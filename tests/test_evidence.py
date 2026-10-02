import base64
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sigstore.errors import VerificationError
from test_api import AP, APPROVER, OP, OPERATOR, payload

from delivery.api import create_app
from delivery.evidence import (
    DEFAULT_REPOSITORY,
    WORKFLOW,
    DemoVerifier,
    EvidenceRejected,
    EvidenceUnavailable,
    GitHubVerifier,
    verify_signature,
)

RELEASE = {
    "evidence_url": f"https://github.com/{DEFAULT_REPOSITORY}/actions/runs/123",
    "commit_sha": "a" * 40,
    "image_digest": "sha256:" + "b" * 64,
}


def workflow(**changes):
    return {
        "repository": {"full_name": DEFAULT_REPOSITORY},
        "head_sha": RELEASE["commit_sha"],
        "head_branch": "main",
        "path": WORKFLOW,
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 1,
        **changes,
    }


def statement(**changes):
    return {
        "predicateType": "https://slsa.dev/provenance/v1",
        "subject": [{"name": f"ghcr.io/{DEFAULT_REPOSITORY}", "digest": {"sha256": "b" * 64}}],
        **changes,
    }


def verifier(run=None, signed=None, status=200, check=None):
    def handler(request):
        if "/actions/runs/" in request.url.path:
            return httpx.Response(status, json=run if run is not None else workflow())
        return httpx.Response(200, json={"attestations": [{"bundle": signed or {"fixture": True}}]})

    return GitHubVerifier(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        signature_check=check or (lambda *args: statement()),
    )


def test_success_is_bound_to_commit_digest_workflow_and_run():
    calls = []

    def check(bundle, repository, commit, invocation):
        calls.append((repository, commit, invocation))
        return statement()

    result = verifier(check=check).verify(RELEASE)
    assert result["verified"] and result["mode"] == "verified"
    assert result["image_digest"] == RELEASE["image_digest"]
    assert calls == [
        (
            DEFAULT_REPOSITORY,
            RELEASE["commit_sha"],
            f"https://github.com/{DEFAULT_REPOSITORY}/actions/runs/123/attempts/1",
        )
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"repository": {"full_name": "untrusted/repo"}},
        {"head_sha": "c" * 40},
        {"head_branch": "feature"},
        {"path": ".github/workflows/untrusted.yml"},
        {"event": "pull_request"},
        {"status": "in_progress"},
        {"conclusion": "failure"},
        {"conclusion": "cancelled"},
        {"run_attempt": 0},
    ],
)
def test_ineligible_workflow_cannot_approve(change):
    with pytest.raises(EvidenceRejected):
        verifier(workflow(**change)).verify(RELEASE)


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/other/repo/actions/runs/123",
        "https://evil.example/actions/runs/123",
        f"https://github.com/{DEFAULT_REPOSITORY}/actions/runs/123?alternate=1",
    ],
)
def test_external_evidence_cannot_select_another_destination(url):
    with pytest.raises(EvidenceRejected):
        verifier().verify({**RELEASE, "evidence_url": url})


@pytest.mark.parametrize(
    ("status", "exception"),
    [(404, EvidenceRejected), (429, EvidenceUnavailable), (503, EvidenceUnavailable)],
)
def test_github_errors_fail_closed(status, exception):
    with pytest.raises(exception):
        verifier(status=status).verify(RELEASE)


@pytest.mark.parametrize(
    "signed",
    [
        statement(predicateType="unexpected"),
        statement(subject=[{"name": "ghcr.io/other/image", "digest": {"sha256": "b" * 64}}]),
        statement(
            subject=[{"name": f"ghcr.io/{DEFAULT_REPOSITORY}", "digest": {"sha256": "c" * 64}}]
        ),
    ],
)
def test_signed_statement_must_match_image_and_predicate(signed):
    with pytest.raises(EvidenceRejected):
        verifier(check=lambda *args: signed).verify(RELEASE)


def test_invalid_signature_is_not_replaced_by_declared_quality_flags(tmp_path):
    def invalid(*args):
        raise ValueError("Signature invalid")

    app = create_app(tmp_path / "verified.db", OPERATOR, APPROVER, verifier(check=invalid))
    with TestClient(app) as client:
        body = {**payload(), **RELEASE}
        item = client.post("/api/v1/releases", json=body, headers=OP).json()
        response = client.post(
            f"/api/v1/releases/{item['id']}/approve", headers=AP, json={"expected_version": 1}
        )
        assert response.status_code == 412
        assert (
            client.get(f"/api/v1/releases/{item['id']}", headers=OP).json()["status"] == "candidate"
        )
        assert len(app.state.store.events(item["id"])) == 1


def test_verified_receipt_is_persisted(tmp_path):
    app = create_app(tmp_path / "verified.db", OPERATOR, APPROVER, verifier())
    with TestClient(app) as client:
        item = client.post("/api/v1/releases", json={**payload(), **RELEASE}, headers=OP).json()
        response = client.post(
            f"/api/v1/releases/{item['id']}/approve", headers=AP, json={"expected_version": 1}
        )
        assert response.status_code == 200
        receipt = json.loads(response.json()["verified_evidence"])
        assert receipt["verified"] and receipt["commit_sha"] == RELEASE["commit_sha"]


def test_unavailable_evidence_preserves_candidate(tmp_path):
    app = create_app(tmp_path / "verified.db", OPERATOR, APPROVER, verifier(status=503))
    with TestClient(app) as client:
        item = client.post("/api/v1/releases", json={**payload(), **RELEASE}, headers=OP).json()
        assert (
            client.post(
                f"/api/v1/releases/{item['id']}/approve", headers=AP, json={"expected_version": 1}
            ).status_code
            == 503
        )
        assert app.state.store.get(item["id"])["version"] == 1


def signed_fixture():
    return json.loads((Path(__file__).parent / "fixtures" / "provenance.json").read_text())


def test_real_signature_certificate_and_transparency_proof():
    result = verify_signature(
        signed_fixture(),
        DEFAULT_REPOSITORY,
        "3069ac8a2b68c7446c064b368dc77781507a8cc2",
        f"https://github.com/{DEFAULT_REPOSITORY}/actions/runs/37051819952/attempts/1",
        offline=True,
    )
    expected = "79d0a62c204fac8981af1d77994ef94ac77daffd697b65bf6a783bba282cd282"
    assert result["subject"][0]["digest"]["sha256"] == expected


def test_tampered_bundle_cannot_pass_crypto_verification():
    bundle = signed_fixture()
    payload = json.loads(base64.b64decode(bundle["dsseEnvelope"]["payload"]))
    payload["subject"][0]["digest"]["sha256"] = "f" * 64
    bundle["dsseEnvelope"]["payload"] = base64.b64encode(json.dumps(payload).encode()).decode()
    with pytest.raises(VerificationError):
        verify_signature(
            bundle,
            DEFAULT_REPOSITORY,
            "3069ac8a2b68c7446c064b368dc77781507a8cc2",
            f"https://github.com/{DEFAULT_REPOSITORY}/actions/runs/37051819952/attempts/1",
            offline=True,
        )


def test_signed_certificate_cannot_be_used_for_another_commit():
    with pytest.raises(VerificationError):
        verify_signature(
            signed_fixture(),
            DEFAULT_REPOSITORY,
            "f" * 40,
            f"https://github.com/{DEFAULT_REPOSITORY}/actions/runs/37051819952/attempts/1",
            offline=True,
        )


def test_demo_approval_cannot_be_promoted_after_switching_to_verified(tmp_path):
    path = tmp_path / "switch.db"
    demo = create_app(path, OPERATOR, APPROVER, DemoVerifier())
    with TestClient(demo) as client:
        item = client.post("/api/v1/releases", json=payload(), headers=OP).json()
        approved = client.post(
            f"/api/v1/releases/{item['id']}/approve", headers=AP, json={"expected_version": 1}
        ).json()
    verified = create_app(path, OPERATOR, APPROVER, verifier())
    with TestClient(verified) as client:
        response = client.post(
            f"/api/v1/releases/{item['id']}/deploy",
            headers=OP,
            json={"expected_version": approved["version"]},
        )
        assert response.status_code == 412
        assert verified.state.store.get(item["id"])["status"] == "approved"


def test_invalid_mode_is_not_a_silent_demo_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_MODE", "unknown")
    with pytest.raises(ValueError):
        create_app(tmp_path / "bad-mode.db", OPERATOR, APPROVER)
