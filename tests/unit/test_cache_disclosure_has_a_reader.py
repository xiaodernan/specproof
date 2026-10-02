"""#145 — the cache disclosure's reader is bound to its producer's key.

Two ends have to agree, and nothing used to check that they did:

- the PRODUCER: `craft/loop.py` projects the sandbox's own cache statement into
  a step's evidence under `cache_note` (the value comes from
  `sandbox/runner.py`, which fills `SandboxResult.cache_note` — an empty note
  means "the profile mounted no cache", never "the cache was verified");
- the READER: `apps/web/src/agent/pages/AgentResult.tsx` renders it under a
  Chinese label.

Until #145 the only way to read that note in the product was to expand the
raw-JSON `<details>` and know the English key name — an honest disclosure that
no reviewer would find — while `craft/gates.py` showed it only for gates that
actually RUN a command. A rename on either side would have re-opened the gap in
silence, which is what this gate prevents.

It also records the measurement behind NOT adding a word table here: the
`CacheCheck.verdict` enum (`use` | `fail` | `rebuild`, `sandbox/cache_verify.py`)
never reaches any payload — `SandboxResult` and `ExecResult` carry `cache_note`
only — so a Chinese label for those three words would be dead code rather than
disclosure. If that enum is ever surfaced, this docstring is the place that
should be updated along with the table.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOOP = REPO / "craft" / "loop.py"
RUNNER = REPO / "sandbox" / "runner.py"
EXECUTOR = REPO / "craft" / "executor.py"
PAGE = REPO / "apps" / "web" / "src" / "agent" / "pages" / "AgentResult.tsx"


def _loop_evidence_keys() -> set[str]:
    """The evidence keys the loop projects into a step's terminal record."""
    text = LOOP.read_text(encoding="utf-8")
    match = re.search(r"for key in \(([^)]*)\)", text)
    assert match, "the loop's evidence projection list moved"
    return set(re.findall(r'"([a-z_]+)"', match.group(1)))


def _page_reads() -> set[str]:
    """The evidence keys the result page reads off a step."""
    return set(re.findall(r"evidence\?\.([A-Za-z_]+)", PAGE.read_text(encoding="utf-8")))


def test_the_producer_still_writes_the_cache_key() -> None:
    assert "cache_note" in _loop_evidence_keys()


def test_the_note_has_a_producer_on_the_sandbox_result() -> None:
    """The loop can only project what the sandbox recorded."""
    runner = RUNNER.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")
    assert "cache_note: str = \"\"" in runner or "cache_note=" in runner
    assert "cache_note: str = \"\"" in executor


def test_the_page_reads_the_key_the_loop_writes() -> None:
    """Both ends, derived — never one side hard-coded against the other."""
    produced = _loop_evidence_keys()
    read = _page_reads()
    assert read, "the result page no longer reads any step evidence key"
    assert read == {"cache_note"}, (
        "the page and the loop disagree about the cache key: "
        f"page reads {sorted(read)}, loop writes {sorted(produced & {'cache_note'})}"
    )
    assert read <= produced, "the page reads a key the loop never writes"


def test_the_label_is_chinese_and_the_panel_is_conditional() -> None:
    """The disclosure must sit under a reader-facing label, and its absence
    must stay silent (no cache mounted) rather than become a reassurance."""
    page = PAGE.read_text(encoding="utf-8")
    assert "依赖缓存完整性" in page, "the labelled panel disappeared"
    assert "cacheNotes.length > 0" in page, (
        "the panel must render only when there is something to disclose"
    )
