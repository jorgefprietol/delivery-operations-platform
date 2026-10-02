"""Verify a completed real release through the production approval API and Sigstore."""

import argparse
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from delivery.api import create_app
from delivery.evidence import DEFAULT_REPOSITORY

parser = argparse.ArgumentParser()
parser.add_argument("--run-id", required=True)
parser.add_argument("--commit", required=True)
parser.add_argument("--digest", required=True)
args = parser.parse_args()
os.environ["EVIDENCE_MODE"] = "verified"
operator, approver = secrets.token_urlsafe(40), secrets.token_urlsafe(40)
with TemporaryDirectory() as directory:
    app = create_app(Path(directory) / "verification.db", operator, approver)
    with TestClient(app) as client:
        payload = {
            "environment": "staging",
            "commit_sha": args.commit,
            "image_digest": args.digest,
            "committed_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            "evidence_url": f"https://github.com/{DEFAULT_REPOSITORY}/actions/runs/{args.run_id}",
            "quality_passed": True,
            "security_passed": True,
            "integration_passed": True,
        }
        created = client.post(
            "/api/v1/releases", json=payload, headers={"Authorization": "Bearer " + operator}
        )
        assert created.status_code == 201, created.text
        result = client.post(
            f"/api/v1/releases/{created.json()['id']}/approve",
            json={"expected_version": 1},
            headers={"Authorization": "Bearer " + approver},
        )
        assert result.status_code == 200, result.text
        receipt = json.loads(result.json()["verified_evidence"])
        assert receipt["verified"] and receipt["mode"] == "verified"
        Path("artifacts").mkdir(exist_ok=True)
        Path("artifacts/verified-evidence.json").write_text(json.dumps(receipt, indent=2))
        print(
            "PASS: successful Actions, exact commit, signed provenance, digest and approval receipt"
        )
