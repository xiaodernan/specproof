"""Investigation Dig — the LLM answers a question about THIS repo, honestly.

Same discipline as the /insight AI 解读 lane:

* **only what the workspace already shows leaves the process** — a bounded
  fact pack (top-level layout + README headings + test count + python file
  count; ≤4 KB); no user secrets, nothing outside the tracked tree;
* **the model may not invent** — empty or thin evidence returns
  UNAVAILABLE honestly (verdict INSUFFICIENT);
* **readonly** — the investigators never write; they only read bounded facts;
* **fail-closed RBAC** — tenant mode + admin/operator only; single-tenant
  deployments answer 503 PROVIDER_UNAVAILABLE like every other admin law;
* **never a verdict** — the model reads the repo; it does not judge it.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 90.0


class InvestigationDigUnavailable(RuntimeError):
    """Raised when the model lane could not produce an answer."""


def _workspace_root():
    from pathlib import Path

    root = os.environ.get("SPECROOF_WORKSPACE")
    return Path(root).resolve() if root else Path.cwd().resolve()


async def generate_investigation_dig(question: str) -> dict[str, Any]:
    """Run the three readonly investigators against the local checkout."""
    if not question.strip():
        raise InvestigationDigUnavailable("question is empty")

    from craft.investigators import investigate

    try:
        result = await investigate(
            _workspace_root(), question, timeout=LLM_TIMEOUT_SECONDS,
        )
    except InvestigationDigUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - unknown failure reads as unavailable
        logger.warning("investigation dig failed: %s: %s", type(exc).__name__, exc)
        raise InvestigationDigUnavailable(
            f"the model lane could not be consulted: {type(exc).__name__}",
        ) from exc

    verdict = result.get("verdict", "INSUFFICIENT")
    agents = [
        {
            "name": a.get("name"),
            "role": a.get("role"),
            "outcome": a.get("outcome"),
            "tokens": a.get("tokens", 0),
        }
        for a in (result.get("agents") or [])
    ]

    usage_total = sum(int(a.get("tokens") or 0) for a in (result.get("agents") or []))

    return {
        "question": result.get("question", question),
        "verdict": verdict,
        "findings": result.get("findings", [])[:12],
        "agents": agents,
        "total_tokens_used": result.get("total_tokens_used", usage_total),
        "duration_ms": result.get("duration_ms", 0),
        "generation_time_ms": result.get("generation_time_ms", 0),
        "model": None,
        "cached": False,
    }
