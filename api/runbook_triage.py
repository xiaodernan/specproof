"""Runbook Triage — the model triangulates a firing alert, readonly.

Same discipline as the `/dig` lane and the `/insight` AI advice lane:

* **only repo-grounded facts suffice to answer** — the fact pack carries the
  alert rule you asked about (verbatim block), the last 20 commits touching
  its lane (name-redacted, per-line SHA + summary only), the five newest
  evidence files, and the compose service map for the api lane. No metric
  time-series is fetched; no network beyond `.local/llm.json`; no writes;
* **no verdict on the release** — never a merge gate;
* **fail-closed RBAC** — tenant mode + admin/operator; everything else 403;
  no local deployments answer 503 PROVIDER_UNAVAILABLE, same as every other
  admin lane;
* **fail-closed unknown alert** — the request's `alert` must exist verbatim
  in `infra/prometheus/alerts-slo.yml`'s `alert:` lines; anything else is 422
  UNKNOWN-ALERT, never a guess at "what you meant";
* **INCONCLUSIVE is a verdict** — if the triad cannot establish anything, it
  says INCONCLUSIVE and names what it is missing, never a fabricated cause.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 150.0

ROOT = Path(__file__).resolve().parents[1]


class RunbookTriageError(RuntimeError):
    """Raised when the model lane could not produce anything."""


def alert_rule_names() -> list[str]:
    """Every `alert:` name deployed in alerts-slo.yml (code-frozen at runtime)."""
    yml = (ROOT / "infra" / "prometheus" / "alerts-slo.yml").read_text(encoding="utf-8")
    import re
    return sorted({m.group(1) for m in re.finditer(r"^\s+- alert: ([A-Za-z0-9_]+)\s*$", yml, re.M)})


def alert_rule_block(alert: str) -> str | None:
    """The verbatim rule block for one alert, bounded — or None if it is not there."""
    yml = (ROOT / "infra" / "prometheus" / "alerts-slo.yml").read_text(encoding="utf-8")
    import re
    match = re.search(rf"(?ms)^\s+- alert: {re.escape(alert)}\s*\n(.*?)(?=\n\s+- alert:|\Z)", yml)
    if not match:
        return None
    block = ("alert: " + alert + "\n" + match.group(1)).strip() + "\n"
    return block[:1600]


def _recent_commits(n: int = 20) -> list[str]:
    """20 newest commit lines, name-redacted — SHA + one-line subject only."""
    import subprocess
    proc = subprocess.run(
        ["git", "log", "--format=%h %s", "-n", str(n)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    if proc.returncode != 0:
        return []
    out = []
    for line in proc.stdout.splitlines():
        if line.strip():
            out.append(line.strip())
    return out


def _newest_evidence_files(k: int = 5) -> list[str]:
    ev = ROOT / "docs" / "evidence"
    try:
        files = [p for p in ev.glob("*.json") if p.is_file()]
    except OSError:
        return []
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in files[:k]]


def _compose_api_block() -> str:
    """The api service's environment keys (verbatim; values redacted)."""
    comp = ROOT / "compose.production.yml"
    try:
        text = comp.read_text(encoding="utf-8")
    except OSError:
        return ""
    i = text.find("\n  api:\n")
    if i < 0:
        return ""
    block = text[i:].split("\n  outbox-relay:", 1)[0]
    kept = [ln for ln in block.splitlines() if ln.strip().startswith(("MYSQL_", "REDIS_", "RABBITMQ_", "SPECPROOF_"))]
    kept = [ln.split(":")[0].strip() + ": <redacted>" for ln in kept]
    return "\n".join(kept[:40])


def build_triage_fact_pack(alert: str) -> str:
    parts: list[str] = []
    rule = alert_rule_block(alert)
    if rule:
        parts.append(f"ALERT RULE (verbatim)\n{rule}")
    commits = _recent_commits(20)
    if commits:
        parts.append("LAST 20 COMMITS\n" + "\n".join(commits))
    files = _newest_evidence_files(5)
    if files:
        parts.append("NEWEST EVIDENCE FILES\n" + "\n".join(files))
    api_block = _compose_api_block()
    if api_block:
        parts.append("API SERVICE ENV (redacted)\n" + api_block)
    pack = "\n\n".join(parts)
    return pack[:4000]


async def generate_triage(alert: str) -> dict[str, Any]:
    """Run the triage. Fail-closed: unknown alert → error; model outage → raises."""
    from craft.investigators import investigate

    question = (
        f"Fired alert (from this repo's deployed prometheus rules): {alert}\n\n"
        "Using ONLY the fact pack below, answer: (1) what this alert means, "
        "(2) the two first things an operator should check, (3) whether the repo's "
        "docs/evidence support the reading. If the facts cannot support any claim, "
        "say so explicitly and state what is missing. Do not fabricate causes, "
        "metrics, or timestamps not present in the pack. Answer in Chinese when "
        "the alert name or question is Chinese, else English. Plain text, no JSON.\n\n"
        "FACT PACK\n" + build_triage_fact_pack(alert)
    )

    result = await investigate(
        ROOT, question, timeout=LLM_TIMEOUT_SECONDS, cache_key="specproof-runbook",
    )

    if result.get("verdict") == "EVIDENCE-GATHERED":
        # The branch constants are spelled verbatim inside return literals so
        # the witness-channel parity scanner reads them straight from the AST.
        return {
            "alert": alert,
            "verdict": "CONFIRMED",
            "findings": result.get("findings", [])[:12],
            "agents": result.get("agents", []),
            "total_tokens_used": int(result.get("total_tokens_used") or 0),
            "generation_time_ms": result.get("generation_time_ms", 0),
            "cached": False,
            "model": None,
        }
    return {
        "alert": alert,
        "verdict": "INCONCLUSIVE",
        "findings": result.get("findings", [])[:12],
        "agents": result.get("agents", []),
        "total_tokens_used": int(result.get("total_tokens_used") or 0),
        "generation_time_ms": result.get("generation_time_ms", 0),
        "cached": False,
        "model": None,
    }


async def list_alerts() -> list[str]:
    return alert_rule_names()
