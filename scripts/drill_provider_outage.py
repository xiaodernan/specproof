"""Drill 2 driver — provider outage degrades honestly (DRILLS.md §2).

Executes for real with zero external services: it points a real
OpenAI-compatible provider at an unreachable endpoint (127.0.0.1:1), runs a
chat call through the real retry policy / circuit breaker, and records the
honest degradation envelope. No secrets are read or written — the api key
is the same "replace_me" placeholder the repo's .env.example uses.

Usage:

    python scripts/drill_provider_outage.py [--json]

Exit codes: 0 = drill PASSED (outage degraded honestly), 1 = drill FAILED.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ops.drills import honest_degradation_report  # noqa: E402
from providers.base import LLMMessage  # noqa: E402
from providers.openai_compatible import OpenAICompatibleProvider  # noqa: E402

UNREACHABLE_BASE_URL = "http://127.0.0.1:1/v1"
#: Dummy credential — never a real secret. The OpenAICompatibleProvider guard
#: refuses "replace_me" by design (honest fail-closed), so the outage drill
#: uses an obviously-fake value pointed at an unreachable endpoint.
DUMMY_API_KEY = "drill-dummy-key-unreachable-endpoint"


def run_outage_drill() -> dict[str, Any]:
    """Provider-level outage: chat against an unreachable endpoint."""
    provider = OpenAICompatibleProvider(
        base_url=UNREACHABLE_BASE_URL,
        api_key=DUMMY_API_KEY,
        model="drill-provider-outage",
        timeout=2.0,
        probe_on_init=False,
        max_retries=0,
    )

    def attempt() -> Any:
        return asyncio.run(
            provider.chat(
                [LLMMessage(role="user", content="drill ping — provider outage")],
                timeout=2.0,
            )
        )

    report = honest_degradation_report(
        attempt,
        max_attempts=3,
        base_backoff=0.25,
        max_backoff=0.5,
        jitter=0.1,
    )
    return report


def run_job_level_drill() -> dict[str, Any]:
    """Job-level outage: the contract compiler at an unreachable provider.

    The rule-based pass runs first and is NEVER discarded; the LLM
    enrichment pass fails against the unreachable endpoint and every
    failure lands in the compile report degrade_reasons — the exact honest
    degradation the pipeline must keep.
    """
    from agent.nodes.compile_contracts import compile_contracts_node

    text = (
        "Authentication requirement:\n"
        "The change-email endpoint must require authentication.\n"
        "Unauthenticated requests must receive 401 Unauthorized.\n"
    )
    state: dict[str, Any] = {
        "requirement_text": text,
        "errors": [],
        "approved_contracts": [],
        "use_llm": True,
        "repo_context": [],
    }
    result = compile_contracts_node(cast(Any, state))
    compile_report = dict(result.get("compile_report") or {})
    return {
        "contracts_produced": len(result.get("contracts", [])),
        "errors_recorded": result.get("errors", []),
        "compile_report": {
            "llm_used": compile_report.get("llm_used"),
            "candidate_count": compile_report.get("candidate_count"),
            "accepted_count": compile_report.get("accepted_count"),
            "degrade_reasons": compile_report.get("degrade_reasons", []),
            "schema_errors": compile_report.get("schema_errors", []),
            "parser_rule_version": compile_report.get("parser_rule_version"),
            "requirement_digest": str(compile_report.get("requirement_digest", ""))[:16],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    args = parser.parse_args()

    # Deterministic drill environment: never inherit a real gateway key.
    env_guard: dict[str, str] = {}
    for var in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        env_guard[var] = os.environ.get(var, "")
    if env_guard["LLM_API_KEY"] not in ("", "replace_me", DUMMY_API_KEY):
        env_guard["LLM_API_KEY"] = "<present-but-not-used>"
    os.environ["LLM_BASE_URL"] = UNREACHABLE_BASE_URL
    os.environ["LLM_API_KEY"] = DUMMY_API_KEY
    os.environ["LLM_MODEL"] = "drill-provider-outage"

    result: dict[str, Any] = {
        "drill": "provider_outage",
        "base_url": UNREACHABLE_BASE_URL,
        "env_guard": env_guard,
    }
    started = time.monotonic()
    try:
        result["provider_level"] = run_outage_drill()
    except Exception as exc:  # noqa: BLE001 — the drill records, never hides
        result["provider_level"] = {"unexpected_error": f"{type(exc).__name__}: {exc}"}
    try:
        result["job_level"] = run_job_level_drill()
    except Exception as exc:  # noqa: BLE001
        result["job_level"] = {"unexpected_error": f"{type(exc).__name__}: {exc}"}
    result["wall_seconds"] = round(time.monotonic() - started, 3)

    provider_report = result.get("provider_level", {})
    if not isinstance(provider_report, dict):
        provider_report = {}
    passed = bool(
        provider_report.get("failure_surfaced")
        and not provider_report.get("result_produced")
        and provider_report.get("elapsed_seconds", 99.0) < 30.0
    )
    result["passed"] = passed
    result["verdict"] = "PASS — provider outage degraded honestly" if passed else "FAIL"

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        print("HONEST_DEGRADATION_VERDICT:", result["verdict"])
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
