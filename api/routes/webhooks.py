"""GitHub webhook ingestion endpoint (P5).

POST /webhooks/github receives GitHub App events. The payload is verified
(X-Hub-Signature-256, constant-time, fail-closed), then pull_request
opened/synchronize/ready_for_review events are converted into verification
jobs through the transactional outbox. Everything else is acknowledged
(202) without action — idempotent, no duplicate jobs for the same delivery.

NOTE: the endpoint is NOT under the jobs API key. It authenticates via the
GitHub webhook secret (GITHUB_WEBHOOK_SECRET), a separate credential.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from typing import Any

from fastapi import APIRouter, Request

from api.errors import AUTH_REQUIRED, PROVIDER_UNAVAILABLE, VALIDATION_FAILED, ApiError
from storage.mysql import MySQLStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_PROCESSED_EVENTS: dict[str, bool] = {}


def _dashboard_job_url(job_id: str) -> str:
    base = os.getenv("SPECPROOF_PUBLIC_URL", "").rstrip("/")
    return f"{base}/dashboard#job={job_id}" if base else ""


def _maybe_publish_initial_check(
    store: MySQLStore, job: dict[str, Any], repo: dict[str, Any]
) -> None:
    """Best-effort: create the specproof/verify Check Run for a PR job.

    GitHub publishing is optional infrastructure — it must never affect job
    acceptance. Missing or misconfigured credentials are logged and skipped.
    """
    from integrations.github_checks import (
        GitHubAppConfigError,
        github_app_client_from_env,
    )

    owner = (repo.get("owner") or {}).get("login", "")
    repo_name = repo.get("name", "")
    if not (owner and repo_name):
        return
    try:
        client = github_app_client_from_env()
    except GitHubAppConfigError as exc:
        logger.warning(
            "GitHub App misconfigured; check run skipped: %s", exc
        )
        return
    if client is None:
        return
    try:
        run = client.create_check_run(
            owner=owner,
            repo=repo_name,
            head_sha=job["head_ref"],
            title="SpecProof verification",
            summary=(
                f"Verification queued for job {job['id']} "
                f"(depth {job.get('depth', 'FAST')})."
            ),
            details_url=_dashboard_job_url(job["id"]),
        )
        store.set_job_github_check(
            job["id"],
            {
                "check_run_id": int(run["id"]),
                "owner": owner,
                "repo": repo_name,
                "head_sha": job["head_ref"],
                "pull_number": repo.get("pull_number"),
            },
        )
    except Exception as exc:  # noqa: BLE001 — optional integration
        logger.warning(
            "GitHub Check Run creation failed for %s: %s", job["id"], exc
        )
    finally:
        client.close()


def _delivery_key(delivery_id: str, event: str) -> str:
    return hashlib.sha256((delivery_id + "|" + event).encode()).hexdigest()


@router.post("/github", status_code=202)
async def github_webhook(request: Request) -> dict[str, Any]:
    """Verify and ingest a GitHub event (pull_request family)."""
    body = await request.body()
    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    event = request.headers.get("X-GitHub-Event", "")

    from integrations.github import verify_signature

    try:
        valid = verify_signature(body, request.headers.get("X-Hub-Signature-256"))
    except Exception as exc:  # noqa: BLE001 — config errors fail closed
        raise ApiError(
            status_code=503, code=PROVIDER_UNAVAILABLE, detail=str(exc),
        ) from exc
    if not valid:
        raise ApiError(
            status_code=401, code=AUTH_REQUIRED, detail="Invalid webhook signature",
        )

    if event not in ("pull_request",):
        return {"accepted": True, "action": "ignored", "event": event}

    try:
        payload = json.loads(body)
        action = payload.get("action", "")
    except json.JSONDecodeError as exc:
        raise ApiError(
            status_code=400, code=VALIDATION_FAILED, detail="Invalid JSON payload",
        ) from exc

    if action not in ("opened", "synchronize", "ready_for_review"):
        return {"accepted": True, "action": "ignored", "event": event, "action_seen": action}

    # Delivery idempotency: the same GitHub delivery must never enqueue
    # the same job twice (at-least-once redelivery is expected).
    dedupe_key = _delivery_key(delivery_id or str(uuid.uuid4()), event)
    if _PROCESSED_EVENTS.get(dedupe_key):
        return {"accepted": True, "action": "duplicate_delivery"}

    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})
    base_ref = (pr.get("base") or {}).get("sha") or (pr.get("base") or {}).get("ref", "")
    head_ref = (pr.get("head") or {}).get("sha") or (pr.get("head") or {}).get("ref", "")
    clone_url = repo.get("clone_url", "")
    if not (base_ref and head_ref and clone_url):
        return {"accepted": True, "action": "skipped", "reason": "missing refs/url"}

    job = {
        "id": str(uuid.uuid4()),
        "repo_path": clone_url,
        "base_ref": base_ref,
        "head_ref": head_ref,
        "spec_path": "",  # filled by the worker from the repo's constitution
        "depth": "FAST",
    }
    try:
        store = MySQLStore()
        store.create_job_with_outbox(job)
    except Exception as exc:  # noqa: BLE001
        raise ApiError(
            status_code=503,
            code=PROVIDER_UNAVAILABLE,
            detail="Job NOT accepted — persistence failed",
        ) from exc

    _maybe_publish_initial_check(
        store, job, {**repo, "pull_number": pr.get("number")}
    )
    _PROCESSED_EVENTS[dedupe_key] = True
    return {
        "accepted": True,
        "action": "job_created",
        "job_id": job["id"],
    }
