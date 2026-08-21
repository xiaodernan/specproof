"""Finding feedback endpoints (Go/No-Go #13 mechanism).

POST /api/v1/jobs/{job_id}/feedback records one accept/reject verdict for
a finding of that job; GET /api/v1/jobs/{job_id}/feedback returns the rows
and the acceptance-rate stats. Gate #13 measures acceptance_rate from
these records across the pilot repositories; findings without feedback
are never counted (silence is not acceptance).

Auth: API key + rate limit, same fail-closed posture as /jobs. The job
must exist in MySQL (404 JOB_NOT_FOUND otherwise); a persistence failure
is a real 503 PROVIDER_UNAVAILABLE — feedback is never acknowledged when
nothing was stored.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from api.auth import enforce_rate_limit, require_api_key
from api.errors import JOB_NOT_FOUND, PROVIDER_UNAVAILABLE, ApiError
from storage.mysql import MySQLStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/jobs",
    tags=["feedback"],
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)


class FeedbackRequest(BaseModel):
    """One accept/reject verdict. Extra fields are refused by pydantic's
    default extra=ignore? No — extra fields raise 422 via FastAPI."""

    finding_id: str = Field(min_length=1, max_length=64)
    contract_id: str = Field(min_length=1, max_length=128)
    severity: str = Field(pattern="^(BLOCKER|MAJOR|MINOR|NEEDS_CONFIRMATION)$")
    verdict: str = Field(pattern="^(accept|reject)$")
    reason: str | None = Field(default=None, max_length=1000)
    created_by: str = Field(min_length=1, max_length=128)

    @field_validator("verdict")
    @classmethod
    def _verdict_must_be_accept_or_reject(cls, v: str) -> str:
        if v not in ("accept", "reject"):
            raise ValueError("verdict must be accept or reject")
        return v


@router.post("/{job_id}/feedback", status_code=201)
async def create_feedback(job_id: str, payload: FeedbackRequest) -> dict[str, Any]:
    """Record one finding verdict. 201 only when the row is persisted."""
    store = MySQLStore()
    try:
        job = store.get_job(job_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mysql unavailable for feedback: %s", exc)
        raise ApiError(
            status_code=503, code=PROVIDER_UNAVAILABLE,
            detail="feedback storage unavailable",
        ) from exc
    if job is None:
        raise ApiError(
            status_code=404, code=JOB_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )
    feedback = {
        "id": str(uuid.uuid4()),
        "job_id": job_id,
        "tenant_id": job.get("tenant_id"),
        "finding_id": payload.finding_id,
        "contract_id": payload.contract_id,
        "severity": payload.severity,
        "verdict": payload.verdict,
        "reason": payload.reason,
        "created_by": payload.created_by,
    }
    try:
        store.insert_feedback(feedback)
    except Exception as exc:  # noqa: BLE001
        logger.warning("feedback insert failed: %s", exc)
        raise ApiError(
            status_code=503, code=PROVIDER_UNAVAILABLE,
            detail="feedback storage unavailable",
        ) from exc
    return {"id": feedback["id"], "job_id": job_id, "verdict": payload.verdict}


@router.get("/{job_id}/feedback")
async def list_feedback(job_id: str) -> dict[str, Any]:
    """Feedback rows plus acceptance-rate stats for one job."""
    store = MySQLStore()
    try:
        job = store.get_job(job_id)
        rows = store.list_feedback(job_id)
        stats = store.feedback_stats(job_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mysql unavailable for feedback: %s", exc)
        raise ApiError(
            status_code=503, code=PROVIDER_UNAVAILABLE,
            detail="feedback storage unavailable",
        ) from exc
    if job is None:
        raise ApiError(
            status_code=404, code=JOB_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )
    return {"job_id": job_id, "rows": rows, "stats": stats}
