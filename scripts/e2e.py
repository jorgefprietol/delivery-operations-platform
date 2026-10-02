"""Exercise the real HTTP service; all registered delivery records are synthetic."""

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:18095")
parser.add_argument("--prometheus-url")
args = parser.parse_args()
if Path(".env").exists():
    for line in Path(".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


def check(response, expected):
    if response.status_code != expected:
        raise RuntimeError(f"Expected {expected}; received {response.status_code}: {response.text}")
    return response.json()


with httpx.Client(base_url=args.base_url, timeout=15) as client:
    operator = {"Authorization": f"Bearer {os.environ['OPERATOR_TOKEN']}"}
    approver = {"Authorization": f"Bearer {os.environ['APPROVER_TOKEN']}"}
    health = check(client.get("/health/ready"), 200)
    if health.get("evidence_mode") != "demo":
        raise RuntimeError("Synthetic E2E requires explicit EVIDENCE_MODE=demo")
    check(client.get("/api/v1/releases"), 401)
    created = []
    for _ in range(2):
        payload = {
            "environment": "production",
            "commit_sha": uuid4().hex + uuid4().hex[:8],
            "image_digest": "sha256:" + uuid4().hex + uuid4().hex,
            "committed_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            "evidence_url": "https://github.com/jorgefprietol/delivery-operations-platform/actions/runs/1",
            "quality_passed": True,
            "security_passed": True,
            "integration_passed": True,
        }
        release = check(client.post("/api/v1/releases", json=payload, headers=operator), 201)
        check(client.post("/api/v1/releases", json=payload, headers=operator), 409)
        root = f"/api/v1/releases/{release['id']}"
        check(client.post(root + "/deploy", json={"expected_version": 1}, headers=operator), 409)
        check(client.post(root + "/approve", json={"expected_version": 1}, headers=operator), 403)
        release = check(
            client.post(root + "/approve", json={"expected_version": 1}, headers=approver), 200
        )
        check(client.post(root + "/deploy", json={"expected_version": 1}, headers=operator), 409)
        release = check(
            client.post(
                root + "/deploy", json={"expected_version": release["version"]}, headers=operator
            ),
            200,
        )
        created.append(release)
    root = f"/api/v1/releases/{created[-1]['id']}"
    release = check(
        client.post(root + "/fail", json={"expected_version": 3}, headers=operator), 200
    )
    check(client.post(root + "/rollback", json={"expected_version": 4}, headers=operator), 200)
    restored = check(client.get(f"/api/v1/releases/{created[0]['id']}", headers=operator), 200)
    assert restored["status"] == "deployed"
    events = check(client.get(root + "/events", headers=operator), 200)
    assert [event["action"] for event in events] == [
        "created",
        "approve",
        "deploy",
        "fail",
        "rollback",
    ]
    summary = check(client.get("/api/v1/summary", headers=operator), 200)
    assert summary["production_deployments"] >= 2
    assert summary["recovered_incidents"] >= 1
    metrics = client.get("/metrics")
    assert metrics.status_code == 200 and "delivery_http_requests_total" in metrics.text
    if args.prometheus_url:
        import time

        for _attempt in range(20):
            result = httpx.get(
                args.prometheus_url + "/api/v1/query",
                params={"query": 'up{job="delivery-api"}'},
                timeout=10,
            ).json()
            if any(item["value"][1] == "1" for item in result["data"]["result"]):
                break
            time.sleep(2)
        else:
            raise RuntimeError("Prometheus did not scrape the API")
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/e2e.json").write_text(
        json.dumps({"result": "passed", "synthetic_records": True, "summary": summary}, indent=2)
    )
    print(
        "PASS: authentication, quality gates, role isolation, concurrency, rollback, audit, metrics"
    )
