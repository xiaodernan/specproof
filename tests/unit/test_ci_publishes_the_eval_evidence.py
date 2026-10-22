"""A workflow that runs the eval must publish the EVIDENCE, not just the page.

The HTML report is a VIEW of the evidence (ledger #411); the evidence is
the sidecar the evaluation writes next to it. The sidecar carries what
the page cannot: the reason a case was never measured, the output of the
side that failed, the number of attempts each case needed, and the
per-case records themselves.

Before this, both workflows uploaded ONLY the page. A run that failed
because a case was never measured therefore left a page and NOTHING to
diagnose it from - the reason and the failing side's output existed for
the length of the job and were then thrown away. The next question ("why
did the base side fail?") could only be answered by running the pool
again, for hours.

``scripts/diagnose_eval_sidecar.py`` (ledger #420) reads exactly those
files, so the sidecar has to be published for the tool to be usable in
CI at all.

These tests are SHARP: dropping the sidecar from a workflow's upload
makes them fail.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

#: A workflow that runs the evaluation writes its sidecars next to the
#: report; these are the files the sidecar lives in.
SIDECARS = (
    "eval-report.results.json",
    "eval-report.results.jsonl",
)

#: The tool that reads them.
DIAGNOSTIC = ROOT / "scripts" / "diagnose_eval_sidecar.py"


def _eval_workflows() -> dict[str, str]:
    """The workflows that run the evaluation, and their text."""
    out: dict[str, str] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        if "cli.specproof.main eval" in text:
            out[path.name] = text
    assert len(out) >= 2, (
        f"expected the evaluation to run in >=2 workflows, found {sorted(out)}"
    )
    return out


def _upload_paths(text: str) -> list[str]:
    """Every path an upload-artifact step publishes (basename)."""
    return [
        Path(p).name
        for p in re.findall(
            r"^\s{10,}([A-Za-z0-9_./-]+\.(?:html|json|jsonl))\s*$", text, re.M
        )
    ]


def test_every_workflow_that_runs_the_eval_publishes_the_sidecar() -> None:
    """The evidence has to travel with the page."""
    for name, text in _eval_workflows().items():
        published = _upload_paths(text)
        for sidecar in SIDECARS:
            assert sidecar in published, (
                f"{name} runs the evaluation but does not publish "
                f"{sidecar}: a failed run would leave a page and nothing to "
                f"diagnose it from"
            )


def test_every_workflow_still_publishes_the_page() -> None:
    """The page is what a human opens; the sidecar is the evidence."""
    for name, text in _eval_workflows().items():
        assert "eval-report.html" in _upload_paths(text), name


def test_the_sidecar_names_are_the_ones_the_tool_reads() -> None:
    """The published files must be the ones the diagnostic tool reads.

    The tool takes the sidecar path as an argument, so this is a naming
    agreement - but a renamed sidecar would silently make the published
    artifact useless, and nobody would notice until a run failed.
    """
    tool = DIAGNOSTIC.read_text(encoding="utf-8")
    assert ".results.json" in tool
    assert ".results.jsonl" in tool


def test_the_evaluation_writes_the_sidecars_beside_the_report() -> None:
    """The sidecar path is derived from the report path.

    The evaluation writes ``<output>.results.json`` and
    ``<output>.results.jsonl``; the workflows publish exactly those, next
    to the page they name. If the derivation changed, the published
    artifacts would be files that do not exist.
    """
    eval_py = (ROOT / "cli" / "specproof" / "commands" / "eval.py").read_text(
        encoding="utf-8"
    )
    assert 'out.with_suffix(".results.json")' in eval_py, (
        "the final sidecar is no longer derived from the report path"
    )
    assert '".results.jsonl"' in eval_py, (
        "the incremental sidecar is no longer derived from the report path"
    )
