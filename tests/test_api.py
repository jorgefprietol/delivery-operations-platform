from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from delivery.api import Candidate, create_app
from delivery.store import Conflict

OPERATOR, APPROVER = "o" * 40, "a" * 40
OP = {"Authorization": "Bearer " + OPERATOR}
AP = {"Authorization": "Bearer " + APPROVER}


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / "delivery.db", OPERATOR, APPROVER)


@pytest.fixture
def client(app):
    with TestClient(app) as value:
        yield value


def payload(environment="production"):
    return {
        "environment": environment,
        "commit_sha": "a" * 40,
        "image_digest": "sha256:" + uuid4().hex + uuid4().hex,
        "committed_at": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
        "evidence_url": "https://github.com/example/platform/actions/runs/123",
        "quality_passed": True,
        "security_passed": True,
        "integration_passed": True,
    }


def register(client, environment="production"):
    response = client.post("/api/v1/releases", json=payload(environment), headers=OP)
    assert response.status_code == 201
    return response.json()


def act(client, release, action, headers=OP, expected=200):
    response = client.post(
        f"/api/v1/releases/{release['id']}/{action}",
        json={"expected_version": release["version"]},
        headers=headers,
    )
    assert response.status_code == expected, response.text
    return response.json()


def deploy(client, environment="production"):
    return act(client, act(client, register(client, environment), "approve", AP), "deploy")


def test_empty_data_and_security(client):
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").json()["status"] == "ready"
    assert client.get("/api/v1/releases").status_code == 401
    assert (
        client.get("/api/v1/releases", headers={"Authorization": "Bearer wrong"}).status_code == 401
    )
    summary = client.get("/api/v1/summary", headers=OP).json()
    assert summary["change_failure_rate"] is None
    assert summary["mean_recovery_time_seconds"] is None
    assert client.get("/api/v1/releases?limit=201", headers=OP).status_code == 422
    assert client.get("/api/v1/summary?days=0", headers=OP).status_code == 422
    assert "delivery_change_failure_ratio_30d" not in client.get("/metrics").text


@pytest.mark.parametrize("action", ["approve", "deploy", "fail", "rollback"])
def test_illegal_transitions(client, action):
    item = register(client)
    if action == "approve":
        act(client, item, action, expected=403)
    else:
        act(client, item, action, expected=409)


def test_role_separation(client):
    assert client.post("/api/v1/releases", json=payload(), headers=AP).status_code == 403
    item = act(client, register(client), "approve", AP)
    act(client, item, "deploy", AP, expected=403)
    assert client.get("/api/v1/releases", headers=AP).status_code == 200


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("environment", "unknown"),
        ("commit_sha", "invalid"),
        ("image_digest", "latest"),
        ("committed_at", datetime.now(UTC).replace(year=2099).isoformat()),
        ("committed_at", "2026-01-01T00:00:00"),
        ("evidence_url", "https://evil.example/actions/runs/1"),
        ("evidence_url", "http://github.com/example/platform/actions/runs/1"),
        ("quality_passed", False),
        ("security_passed", False),
        ("integration_passed", False),
        ("unknown", "extra"),
    ],
)
def test_invalid_candidates(client, field, value):
    body = payload()
    body[field] = value
    assert client.post("/api/v1/releases", json=body, headers=OP).status_code == 422


def test_duplicate_digest_and_optimistic_concurrency(client):
    body = payload()
    item = client.post("/api/v1/releases", json=body, headers=OP).json()
    assert client.post("/api/v1/releases", json=body, headers=OP).status_code == 409
    act(client, item, "approve", AP)
    act(client, item, "deploy", expected=409)


def test_end_to_end_recovery_and_audit(client):
    first = deploy(client)
    second = deploy(client)
    second = act(client, second, "fail")
    summary = client.get("/api/v1/summary", headers=OP).json()
    assert summary["production_deployments"] == 2
    assert summary["change_failure_rate"] == 0.5
    assert summary["open_incidents"] == 1
    assert summary["mean_recovery_time_seconds"] is None
    second = act(client, second, "rollback")
    assert second["status"] == "rolled_back"
    restored = client.get(f"/api/v1/releases/{first['id']}", headers=OP).json()
    assert restored["status"] == "deployed"
    assert restored["version"] == 5
    summary = client.get("/api/v1/summary", headers=AP).json()
    assert summary["recovered_incidents"] == 1 and summary["open_incidents"] == 0
    assert summary["mean_lead_time_seconds"] >= 600
    assert summary["mean_recovery_time_seconds"] >= 0
    events = client.get(f"/api/v1/releases/{second['id']}/events", headers=OP).json()
    assert [row["action"] for row in events] == ["created", "approve", "deploy", "fail", "rollback"]
    assert [row["actor"] for row in events] == [
        "operator",
        "approver",
        "operator",
        "operator",
        "operator",
    ]
    assert "delivery_change_failure_ratio_30d 0.5" in client.get("/metrics").text


def test_initial_failure_requires_replacement(client):
    failed = act(client, deploy(client), "fail")
    act(client, failed, "rollback", expected=409)
    replacement = deploy(client)
    assert replacement["previous_id"] is None
    summary = client.get("/api/v1/summary", headers=OP).json()
    assert summary["recovered_incidents"] == 1 and summary["open_incidents"] == 0
    failed = act(client, replacement, "fail")
    act(client, failed, "rollback", expected=409)


def test_failed_predecessor_is_skipped(client):
    first = deploy(client)
    act(client, deploy(client), "fail")
    replacement = deploy(client)
    assert replacement["previous_id"] == first["id"]
    act(client, act(client, replacement, "fail"), "rollback")
    assert client.get(f"/api/v1/releases/{first['id']}", headers=OP).json()["status"] == "deployed"


def test_environment_isolation(client):
    production = deploy(client)
    deploy(client, "staging")
    summary = client.get("/api/v1/summary", headers=OP).json()
    assert summary["production_deployments"] == 1
    assert len(summary["active"]) == 2
    assert (
        client.get(f"/api/v1/releases/{production['id']}", headers=OP).json()["status"]
        == "deployed"
    )


def test_not_found_and_static_assets(client):
    assert client.get("/api/v1/releases/missing", headers=OP).status_code == 404
    assert client.get("/api/v1/releases/missing/events", headers=OP).status_code == 404
    assert (
        client.post(
            "/api/v1/releases/missing/approve", json={"expected_version": 1}, headers=AP
        ).status_code
        == 404
    )
    for path in ("/", "/assets/app.js", "/assets/style.css", "/openapi.json"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["X-Request-ID"]
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert client.get("/assets/invalid").status_code == 422
    assert client.get("/absent").status_code == 404


def test_persistence_after_restart(client, app, tmp_path):
    release = deploy(client)
    other = create_app(tmp_path / "delivery.db", OPERATOR, APPROVER)
    with TestClient(other) as restarted:
        assert restarted.get(f"/api/v1/releases/{release['id']}", headers=OP).json() == release


def test_real_concurrent_approval_has_one_winner(app):
    store = app.state.store
    release = store.create(Candidate(**payload()), "operator")

    def approve(_):
        try:
            store.transition(release["id"], "approve", 1, "approver")
            return "ok"
        except Conflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(approve, range(2))) == ["conflict", "ok"]
    assert len(store.events(release["id"])) == 2


@pytest.mark.parametrize("tokens", [("short", "long" * 10), (OPERATOR, OPERATOR)])
def test_invalid_configuration_fails_closed(tmp_path, tokens):
    with pytest.raises(RuntimeError), TestClient(create_app(tmp_path / "bad.db", *tokens)):
        pass


def test_database_failure_is_observable(client, app, monkeypatch):
    def unavailable(*args):
        raise RuntimeError("private database detail")

    monkeypatch.setattr(app.state.store, "get", unavailable)
    response = client.get("/api/v1/releases/any", headers=OP)
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal service error"}
    assert "private database detail" not in response.text
    assert 'status="500"' in client.get("/metrics").text
    monkeypatch.setattr(app.state.store, "connect", unavailable)
    assert client.get("/health/ready").status_code == 503
