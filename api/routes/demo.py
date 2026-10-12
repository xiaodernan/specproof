"""Demo repository preparation endpoint (roadmap Phase 1.3, backend half).

Web "新建验证" offers a "填入演示案例" shortcut that assumes the bundled
demo repo (``demo/spring-backend``) already carries the ``base`` / ``head-v1``
git refs. Those refs are created by :func:`prepare_demo_repo` (also invoked by
``specproof demo`` and the ``start_local`` hooks). When the refs are missing —
e.g. the operator started the light-weight mode and skipped the hooks, or
pointed the UI at a fresh clone — the shortcut fails with a bare git error and
the operator is sent to a terminal.

This endpoint lets the UI request ref creation on demand. It is a thin,
authenticated wrapper over the existing, tested ``prepare_demo_repo``; it
performs **no verification execution** and never fabricates a verdict, so it
stays clear of the verification-execution security surface (``api/routes/jobs.py``
red line). It is a local setup convenience over the same demo repo the CLI
already mutates.

Layout:
  POST /api/v1/demo/prepare   create base/head-v1 refs if absent (idempotent)
"""

from __future__ import annotations

import logging

import click
from fastapi import APIRouter, Depends

from api.auth import enforce_rate_limit, require_api_key
from api.errors import VALIDATION_FAILED, ApiError
from cli.specproof.commands.demo import (
    BASE_REF,
    DEMO_REPO,
    HEAD_REF,
    prepare_demo_repo,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/demo",
    tags=["demo"],
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)


@router.post("/prepare")
def prepare_demo() -> dict[str, object]:
    """Ensure the demo repo carries the ``base`` / ``head-v1`` refs.

    Idempotent: when both refs already exist no git state is touched and the
    response reports ``created: false``. On a genuine setup error (missing demo
    directory, missing spec file, or the guard annotation already removed from
    the source) the underlying command raises a click error, which is surfaced
    as 422 with the original human-readable message — never a fabricated
    success.
    """
    try:
        created = prepare_demo_repo()
    except click.ClickException as exc:
        raise ApiError(
            status_code=422,
            code=VALIDATION_FAILED,
            detail=str(exc.message),
        ) from exc

    return {
        "created": bool(created),
        "refs": [BASE_REF, HEAD_REF],
        "repo": str(DEMO_REPO),
        "message": (
            "演示仓库引用已就绪 (base / head-v1)。"
            if created
            else "演示仓库引用已存在 (base / head-v1)，无需重建。"
        ),
    }
