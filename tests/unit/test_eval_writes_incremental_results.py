"""A killed evaluation must not take its measurements with it.

The full golden-case evaluation takes hours (the 2026-10-22 DEEP
measurement was 1450 s for ONE case; the pool is ~87 measured cases).
The report and the results sidecar are written at the END of the run, so
a run that is killed - a CI job hitting its timeout, a machine
rebooting, a laptop closing - leaves NOTHING behind, and the only way
to learn those hours is to measure them again.

The incremental sidecar fixes that: one JSON line per case, written and
flushed the moment the case finishes. These tests pin:

- a record is on disk as soon as it is appended (not at the end);
- a torn last line (the kill landed in the middle of a write) is
  skipped, not fatal - the cases before it are still worth having;
- the sidecar is found next to the report the eval writes.
"""

from __future__ import annotations

import json

from cli.specproof.commands.eval import (
    append_incremental_result,
    incremental_results_path,
    read_incremental_results,
)


def test_the_sidecar_sits_next_to_the_report(tmp_path):
    out = tmp_path / "eval-report.html"
    assert incremental_results_path(out) == tmp_path / "eval-report.results.jsonl"


def test_a_record_is_readable_as_soon_as_it_is_appended(tmp_path):
    path = incremental_results_path(tmp_path / "eval-report.html")
    handle = path.open("w", encoding="utf-8")
    try:
        append_incremental_result(handle, {"case": "case-01", "verdict": "PASS"})
        # Read BEFORE the handle is closed: the point of the sidecar is
        # that the evidence exists while the run is still going.
        assert read_incremental_results(path) == [
            {"case": "case-01", "verdict": "PASS"}
        ]
        append_incremental_result(handle, {"case": "case-02", "verdict": "MISS"})
    finally:
        handle.close()
    assert [r["case"] for r in read_incremental_results(path)] == [
        "case-01",
        "case-02",
    ]


def test_a_torn_last_line_is_skipped_not_fatal(tmp_path):
    """The kill landed in the middle of a write: half a line is not a
    record, and it must not take the earlier records with it."""
    path = incremental_results_path(tmp_path / "eval-report.html")
    with path.open("w", encoding="utf-8") as handle:
        append_incremental_result(handle, {"case": "case-01", "verdict": "PASS"})
        append_incremental_result(handle, {"case": "case-02", "verdict": "MISS"})
    # Simulate the kill: the last line is half written.
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"case": "case-03", "verdi')
    records = read_incremental_results(path)
    assert [r["case"] for r in records] == ["case-01", "case-02"]


def test_a_missing_sidecar_reads_as_empty(tmp_path):
    assert read_incremental_results(tmp_path / "nope.jsonl") == []


def test_one_line_is_one_json_object(tmp_path):
    path = incremental_results_path(tmp_path / "eval-report.html")
    handle = path.open("w", encoding="utf-8")
    try:
        append_incremental_result(handle, {"case": "case-01", "note": "含中文"})
    finally:
        handle.close()
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 1
    assert json.loads(lines[0])["note"] == "含中文"
