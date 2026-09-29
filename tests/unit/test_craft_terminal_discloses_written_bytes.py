"""#132 — a STUCK verdict must disclose the bytes that actually reached disk.

Measured premise (the reason the first attempt was reverted): the terminal
disclosure line asserted "the fix did not take" while carrying only the
checker's stdout. Sourcing the digest from ``step.target_files`` rendered
``written_bytes={}`` on this very path, because the deterministic test step
targets no files at all — a field that looks like evidence and proves nothing.

The population is therefore the Editor's own audit, the same list ``_finish``
derives ``report.diff_stat`` from, so the check-time evidence cannot drift from
the published diff.

Predictions before running:

1. a fix that really writes different bytes -> STUCK, ``written_bytes`` holds
   ``calc.py`` with the digest of the bytes now on disk, and that digest is NOT
   the digest of the pre-fix text;
2. a fix whose anchor rewrites identical content -> STUCK, and the disclosure
   still equals the bytes on disk. Measured here (and why this case is written
   the way it is): that pair was NOT byte-identical — 81B became 87B, i.e. the
   Editor re-wrote the file's line endings on this Windows host. So the
   host-neutral invariant this case pins is "disclosure == disk", while the
   content check says the logic did not move. The encoding rewrite itself is a
   separate defect (#133), not something to assert away;
3. the WARNING line and the report evidence carry the same digest string (one
   dict, two readers).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pytest

from craft.editor import Editor
from craft.loop import CraftLoop
from craft.planner import Step, compile_plan
from craft.spec import parse_spec_text

SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"
BEFORE = (
    "def double(x):\n    return x / 2\n\n\ndef greeting(name):\n"
    '    return "hello " + name\n'
)


def _digest(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(raw).hexdigest()[:12]}/{len(raw)}B"


def _write_repo(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(BEFORE, encoding="utf-8")
    (tmp_path / "test_calc.py").write_text(
        "from calc import double, greeting\n\n\n"
        "def test_double():\n    assert double(4) == 8\n\n\n"
        'def test_greeting():\n    assert greeting("a") == "hello a"\n',
        encoding="utf-8",
    )


def _run(
    tmp_path: Path, fix
) -> tuple[dict[str, object], Path]:
    _write_repo(tmp_path)
    spec = parse_spec_text(SPEC)
    loop = CraftLoop(
        spec,
        compile_plan(spec),
        tmp_path,
        job_id="job-132",
        fix_registry={"test": fix},
        exec_mode="local",
    )
    return loop.run(), tmp_path / "calc.py"


def _s3_evidence(report: dict[str, object]) -> dict[str, object]:
    steps = {step["id"]: step for step in report["steps"]}  # type: ignore[index]
    return steps["s3"]["evidence"]  # type: ignore[return-value]


def wrong_but_real(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    assert step.id == "s3" and diagnosis
    editor.apply_edit("calc.py", "return x / 2", "return x - 1")
    return ["calc.py"]


def identical_rewrite(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    assert step.id == "s3" and diagnosis
    editor.apply_edit("calc.py", "return x / 2", "return x / 2")
    return ["calc.py"]


# ── 1. the bytes that landed are named ───────────────────────────


def test_a_stuck_verdict_discloses_the_bytes_that_reached_disk(
    tmp_path: Path,
) -> None:
    report, calc = _run(tmp_path, wrong_but_real)
    assert report["result"] == "STUCK", (
        "this case exists to read a terminal disclosure; a non-terminal answer "
        f"means the fixture no longer reaches the stuck path: {report['result']}"
    )
    written = _s3_evidence(report)["written_bytes"]
    assert isinstance(written, dict) and written, (
        "an empty disclosure is the vacuous field this unit replaced: "
        f"{written!r}"
    )
    on_disk = calc.read_bytes()
    assert written == {"calc.py": _digest(on_disk)}, (
        f"the disclosure must equal the workspace's own bytes {on_disk!r}: "
        f"{written!r}"
    )
    assert written["calc.py"] != _digest(BEFORE.encode("utf-8")), (
        "the field must track the write, not restate the input"
    )


# ── 2. the contrast case: written, but nothing changed ───────────


def test_a_stuck_from_a_no_op_write_discloses_the_bytes_on_disk(
    tmp_path: Path,
) -> None:
    report, calc = _run(tmp_path, identical_rewrite)
    assert report["result"] == "STUCK"
    written = _s3_evidence(report)["written_bytes"]
    on_disk = calc.read_bytes()
    assert written == {"calc.py": _digest(on_disk)}, (
        f"the disclosure must agree with the workspace's own bytes {on_disk!r}: "
        f"{written!r}"
    )
    assert "return x / 2" in calc.read_text(encoding="utf-8"), (
        "the fix re-wrote identical CONTENT, so the only honest reading of a "
        "changed digest is that the write touched the encoding, not the logic"
    )


# ── 3. one dict, two readers ────────────────────────────────────


def test_the_disclosure_line_and_the_report_carry_the_same_digest(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    report, _calc = _run(tmp_path, wrong_but_real)
    expected = _s3_evidence(report)["written_bytes"]["calc.py"]  # type: ignore[index]
    lines = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING and "的终态" in record.getMessage()
    ]
    assert lines, (
        "the terminal verdict no longer logs the deciding check — the console "
        "reader lost the disclosure"
    )
    assert any(f"written_bytes={'{'}'calc.py': '{expected}" in line for line in lines), (
        f"the log line must render the same digest the report carries "
        f"({expected!r}), not a second source: {lines}"
    )
