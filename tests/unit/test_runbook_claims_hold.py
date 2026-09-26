"""#88 — the runbook's operational promises must be checkable, not just written.

`docs/architecture/DATA_DICTIONARY.md` has had a parity gate since #80, so a
migration can no longer land without a schema entry. `docs/operations/RUNBOOK.md`
had none, and #79 measured what that costs: §2 asserted

    生产必须 SPECPROOF_ENV=production — config_guard 拒绝默认口令
    (specproof_pass / replace_me) fail-fast。

while no deployment file set `SPECPROOF_ENV`, so the guard named in that sentence
could never run; the same bullet block also stated the migration range as
"当前 0001-0004" when the repo was at 0012. A confident document is the worst
kind of stale artefact, because it stops the reader from checking.

These tests read the runbook against the deployment files and the migration
directory. The requirement style is deliberately narrow — a claim only counts
when the runbook states it in a form a machine can match — so the gate fails on
drift instead of inventing obligations the doc never promised.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNBOOK = REPO / "docs" / "operations" / "RUNBOOK.md"
DEPLOYMENT_FILES = (
    REPO / "compose.phase0.yml",
    REPO / "compose.production.yml",
    REPO / "compose.observability.yml",
    REPO / "scripts" / "start_local.ps1",
    REPO / "scripts" / "start_local_light.ps1",
)

MIGRATIONS_DIR = REPO / "infra" / "mysql" / "migrations"

#: "当前 0001-0012" — the range end the runbook claims.
_RANGE_RE = re.compile(r"当前\s*0001-(\d{4})")
#: "生产必须 SPECPROOF_ENV=production" — only the runbook's own obligation
#: wording counts. A looser `VAR=value` match landed on the §3 table row
#: `SPECPROOF_SANDBOX=local_fallback`, which is a description of a fallback,
#: not a promise something must set.
_OBLIGATION_RE = re.compile(r"生产必须\s+(.*)$", re.M)
_REQUIREMENT_RE = re.compile(r"([A-Z][A-Z0-9_]{3,})=([A-Za-z][A-Za-z0-9_-]*)")


def _runbook() -> str:
    text = RUNBOOK.read_text(encoding="utf-8")
    assert len(text) > 2000, "RUNBOOK.md looks truncated — the probe is useless"
    return text


def _deployment_text() -> str:
    parts = []
    for path in DEPLOYMENT_FILES:
        assert path.exists(), f"{path.name} moved; this gate would silently stop covering it"
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_the_runbooks_migration_range_is_the_real_one() -> None:
    stated = _RANGE_RE.search(_runbook())
    assert stated is not None, (
        "RUNBOOK no longer states its migration range; the sentence that used "
        "to say it is what this gate checks"
    )
    newest = max(MIGRATIONS_DIR.glob("*.sql")).name[:4]
    assert stated.group(1) == newest, (
        f"RUNBOOK §2 says the schema is at 0001-{stated.group(1)} but the newest "
        f"migration is {newest}; an operator reading it would look for tables "
        "that exist and conclusions that no longer hold"
    )


def test_every_documented_required_value_is_set_by_a_deployment_file() -> None:
    """The #79 lesson as a rule: a `VAR=value` the runbook says production must
    have is only real if some compose file or start script actually sets it."""
    doc = _runbook()
    deployment = _deployment_text()
    claims = {
        pair
        for line in _OBLIGATION_RE.findall(doc)
        for pair in _REQUIREMENT_RE.findall(line)
    }
    assert claims, "RUNBOOK no longer states any 生产必须 VAR=value obligation"
    unwired: list[str] = []
    for var, value in claims:
        set_it = (
            re.search(rf"\b{var}:\s*.*{re.escape(value)}", deployment)
            or re.search(rf'\$env:{var}\s*=\s*"{re.escape(value)}"', deployment)
            or re.search(rf"{var}={re.escape(value)}\b", deployment)
        )
        if not set_it:
            unwired.append(f"{var}={value}")
    assert not unwired, (
        f"RUNBOOK states these as required in production, but no deployment file "
        f"sets them, so whatever depends on them is inert: {sorted(set(unwired))}"
    )


def _credential_like(tokens: set[str]) -> set[str]:
    """Keep credential names and the workspace key; drop prose tokens.

    Without this filter the sentence describing this very gate contributed
    `RUNBOOK` to the "documented list" and the comparison became a text match
    rather than a credential match.
    """
    return {t for t in tokens if t.endswith(("_PASSWORD", "_USER")) or t == "SPECPROOF_API_KEY"}


def test_the_runbooks_credential_checklist_is_what_compose_actually_requires() -> None:
    """The list an operator copies from must equal the list compose refuses to
    start without — a shorter doc means a surprise failure, a longer one means
    the doc was written before the file changed."""
    doc = _runbook()
    section = doc[doc.index("部署可见的变更") :].split("\n\n")[0]
    listed = _credential_like(set(re.findall(r"\b([A-Z][A-Z0-9_]{3,})\b", section)))
    required = _credential_like(
        {
            m.group(1)
            for m in re.finditer(
                r"\b([A-Z][A-Z0-9_]{3,}): \$\{\1:\?", _deployment_text()
            )
        }
    )
    assert required, "compose.production.yml asks for nothing — the probe is broken"
    assert listed == required, (
        f"RUNBOOK lists {sorted(listed - required)} that compose does not require; "
        f"compose requires {sorted(required - listed)} that the RUNBOOK omits"
    )
