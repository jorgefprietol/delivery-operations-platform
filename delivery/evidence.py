"""Verify release eligibility against GitHub and signed Sigstore provenance."""

import json
import os
import re
from datetime import UTC, datetime

import httpx

DEFAULT_REPOSITORY = "jorgefprietol/delivery-operations-platform"
WORKFLOW = ".github/workflows/ci.yml"


class EvidenceRejected(Exception):
    pass


class EvidenceUnavailable(Exception):
    pass


class DemoVerifier:
    mode = "demo"

    def verify(self, release):
        return {"mode": "demo", "verified": False, "checked_at": datetime.now(UTC).isoformat()}


def verify_signature(bundle, repository, commit_sha, invocation, *, offline=False):
    from sigstore.models import Bundle
    from sigstore.verify import Verifier
    from sigstore.verify.policy import (
        AllOf,
        Identity,
        OIDCRunInvocationURI,
        OIDCRunnerEnvironment,
        OIDCSourceRepositoryDigest,
        OIDCSourceRepositoryRef,
        OIDCSourceRepositoryURI,
    )

    policy = AllOf(
        [
            Identity(
                identity=f"https://github.com/{repository}/{WORKFLOW}@refs/heads/main",
                issuer="https://token.actions.githubusercontent.com",
            ),
            OIDCSourceRepositoryURI(f"https://github.com/{repository}"),
            OIDCSourceRepositoryDigest(commit_sha),
            OIDCSourceRepositoryRef("refs/heads/main"),
            OIDCRunInvocationURI(invocation),
            OIDCRunnerEnvironment("github-hosted"),
        ]
    )
    content_type, payload = Verifier.production(offline=offline).verify_dsse(
        Bundle.from_json(json.dumps(bundle)), policy
    )
    if content_type != "application/vnd.in-toto+json":
        raise EvidenceRejected("Unexpected signed statement content type")
    return json.loads(payload)


class GitHubVerifier:
    mode = "verified"

    def __init__(self, repository=DEFAULT_REPOSITORY, *, client=None, signature_check=None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Invalid evidence repository")
        self.repository = repository
        self.client = client
        self.signature_check = signature_check or verify_signature

    @staticmethod
    def fetch(client, path):
        try:
            response = client.get("https://api.github.com" + path)
            if response.status_code == 404:
                raise EvidenceRejected("Evidence was not found in the trusted repository")
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise EvidenceUnavailable(
                "GitHub evidence is unavailable; approval remains blocked"
            ) from error

    def verify(self, release):
        expected_prefix = f"https://github.com/{self.repository}/actions/runs/"
        match = re.fullmatch(re.escape(expected_prefix) + r"([1-9][0-9]*)", release["evidence_url"])
        if match is None:
            raise EvidenceRejected("Evidence must identify a run in the configured repository")
        run_id = match[1]
        if self.client is not None:
            return self._verify(self.client, release, run_id)
        with httpx.Client(
            timeout=15,
            follow_redirects=False,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                **(
                    {"Authorization": "Bearer " + os.environ["EVIDENCE_GITHUB_TOKEN"]}
                    if os.getenv("EVIDENCE_GITHUB_TOKEN")
                    else {}
                ),
            },
        ) as client:
            return self._verify(client, release, run_id)

    def _verify(self, client, release, run_id):
        prefix = f"/repos/{self.repository}"
        run = self.fetch(client, f"{prefix}/actions/runs/{run_id}")
        if not (
            run.get("repository", {}).get("full_name") == self.repository
            and run.get("head_sha") == release["commit_sha"]
            and run.get("head_branch") == "main"
            and run.get("path") == WORKFLOW
            and run.get("event") in {"push", "workflow_dispatch"}
            and run.get("status") == "completed"
            and run.get("conclusion") == "success"
            and isinstance(run.get("run_attempt"), int)
            and run["run_attempt"] >= 1
        ):
            raise EvidenceRejected(
                "The configured main workflow must succeed for this exact commit"
            )
        bundles = self.fetch(client, f"{prefix}/attestations/{release['image_digest']}")
        invocation = (
            f"https://github.com/{self.repository}/actions/runs/{run_id}"
            f"/attempts/{run['run_attempt']}"
        )
        for attestation in bundles.get("attestations", [])[:30]:
            try:
                statement = self.signature_check(
                    attestation["bundle"], self.repository, release["commit_sha"], invocation
                )
                matches = statement.get(
                    "predicateType"
                ) == "https://slsa.dev/provenance/v1" and any(
                    subject.get("name") == f"ghcr.io/{self.repository}"
                    and subject.get("digest", {}).get("sha256") == release["image_digest"][7:]
                    for subject in statement.get("subject", [])
                )
                if not matches:
                    continue
            except Exception:
                # Bad or unverifiable bundles never authorize a state transition.
                continue
            return {
                "mode": "verified",
                "verified": True,
                "repository": self.repository,
                "run_id": run_id,
                "run_attempt": run["run_attempt"],
                "workflow": WORKFLOW,
                "commit_sha": release["commit_sha"],
                "image_digest": release["image_digest"],
                "invocation": invocation,
                "checked_at": datetime.now(UTC).isoformat(),
            }
        raise EvidenceRejected(
            "No valid signed provenance binds this digest to the trusted workflow run"
        )
