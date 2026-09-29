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
2. a fix whose anchor rewrites identical content -> STUCK, the file stays
   byte-for-byte equal to its own bytes, and the disclosure therefore equals
   the pre-fix digest. Paired with (1) that is what makes the field
   discriminating: the same key, two different answers, and only the write
   moved between them.

   Correction kept on the record because it is how this case got written: the
   first run of this case showed 81B becoming 87B, and I booked that as an
   Editor line-ending defect. Measured directly it was the opposite — with an
   LF fixture and with a CRLF fixture, an identical ``apply_edit`` left the
   file ``byte_identical=True`` in both. The 6 extra bytes were this test's own
   ``write_text`` (newline=None translates "\n" to the host separator), so the
   fixture lied about its plane, not the Editor. Hence newline="\n" above and
   no assertion about re-encoding here.
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
    # newline="\n" on purpose: Path.write_text defaults to newline=None, which
    # re-writes "\n" as the host separator, so an LF fixture silently becomes a
    # CRLF file on Windows. The disclosure cases below compare digests, so the
    # fixture must say what it means on every host.
    (tmp_path / "calc.py").write_text(BEFORE, encoding="utf-8", newline="\n")
    (tmp_path / "test_calc.py").write_text(
        "from calc import double, greeting\n\n\n"
        "def test_double():\n    assert double(4) == 8\n\n\n"
        'def test_greeting():\n    assert greeting("a") == "hello a"\n',
        encoding="utf-8",
        newline="\n",
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
    assert on_disk == BEFORE.encode("utf-8"), (
        "an identical replacement must leave the file byte-for-byte as it was; "
        "the Editor detects the file's own line style and writes that style "
        f"back: {on_disk!r}"
    )
    assert written == {"calc.py": _digest(on_disk)}, (
        f"the disclosure must agree with the workspace's own bytes {on_disk!r}: "
        f"{written!r}"
    )
    assert written["calc.py"] == _digest(BEFORE.encode("utf-8")), (
        "paired with the previous case, this is what gives the field its "
        f"discriminating power: {written!r}"
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
