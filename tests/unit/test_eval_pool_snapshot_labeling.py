"""#252 — every eval reading is labelled with a pool snapshot.

A sidecar that records only the case-set *mode* (tuning / all_not_isolated /
holdout_only) is not enough: a 4-case CI run and a 90-case full-pool run would
both look like "a run happened", and their numbers could be diffed by accident
(#77, #251). The pool snapshot fingerprints exactly what was measured — repo
revision, the kept case list, the positive/negative split, and the floors — so a
4-case run and a 90-case run are unambiguously different artifacts.

These tests pin the snapshot derivation on isolated fixtures (no pipeline, no
Docker). The split rule mirrors the run loop: a case with no / unreadable
ground-truth.json is negative (should_detect defaults to False).
"""

import json
from pathlib import Path

from cli.specproof.commands.eval import _pool_snapshot, _repo_head_sha


def _write_case(root: Path, name: str, *, should_detect: bool | None) -> Path:
    d = root / name
    d.mkdir()
    (d / "spec.md").write_text("# spec\n", encoding="utf-8")
    if should_detect is not None:
        (d / "ground-truth.json").write_text(
            json.dumps({"should_detect": should_detect}), encoding="utf-8"
        )
    return d


def _floors(**over):
    base = {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "min_f1": 1.0,
        "max_false_positives": 0,
        "min_positive_cases": 10,
        "min_negative_cases": 5,
    }
    base.update(over)
    return base


def test_repo_head_sha_is_unknown_for_a_non_git_dir(tmp_path):
    # tmp_path is not a git checkout, so the snapshot must not pretend to know
    # the revision — 'unknown' is the honest answer.
    assert _repo_head_sha(str(tmp_path)) == "unknown"


def test_snapshot_counts_positive_and_negative_cases(tmp_path):
    # 2 positive + 1 negative = the shape of a tiny but valid pool.
    a = _write_case(tmp_path, "case-01", should_detect=True)
    b = _write_case(tmp_path, "case-09", should_detect=True)
    c = _write_case(tmp_path, "case-05", should_detect=False)
    floors = _floors()

    snap = _pool_snapshot(
        str(tmp_path), [c, a, b],  # deliberately out of order to prove sorting
        **floors,
    )

    assert snap["total_kept"] == 3
    assert snap["positive_cases"] == 2
    assert snap["negative_cases"] == 1
    assert snap["case_names"] == ["case-01", "case-05", "case-09"]
    # repo_sha honest for a non-git dir:
    assert snap["repo_sha"] == "unknown"


def test_snapshot_treats_missing_ground_truth_as_negative(tmp_path):
    # A case with no ground-truth.json is counted as negative, exactly like the
    # run loop (should_detect defaults to False there too).
    d = _write_case(tmp_path, "case-07", should_detect=None)
    snap = _pool_snapshot(str(tmp_path), [d], **_floors())
    assert snap["positive_cases"] == 0
    assert snap["negative_cases"] == 1


def test_snapshot_treats_unreadable_ground_truth_as_negative(tmp_path, monkeypatch):
    # An unreadable ground-truth.json must not crash the snapshot; the case
    # degrades to negative (mirrors the run loop's skip-with-reason behaviour).
    d = _write_case(tmp_path, "case-03", should_detect=True)

    def _boom(*_a, **_k):
        raise PermissionError("transient lock")

    monkeypatch.setattr(Path, "read_text", _boom)
    snap = _pool_snapshot(str(tmp_path), [d], **_floors())
    assert snap["positive_cases"] == 0
    assert snap["negative_cases"] == 1


def test_snapshot_carries_the_floors_verbatim(tmp_path):
    a = _write_case(tmp_path, "case-01", should_detect=True)
    # CI weakens its floors to 3/1 — the snapshot must record that, so a CI
    # reading is distinguishable from a 10/5 reading.
    floors = _floors(
        min_recall=1.0, min_precision=1.0, min_f1=1.0,
        max_false_positives=0, min_positive_cases=3, min_negative_cases=1,
    )
    snap = _pool_snapshot(str(tmp_path), [a], **floors)
    assert snap["floors"] == {
        "min_recall": 1.0,
        "min_precision": 1.0,
        "min_f1": 1.0,
        "max_false_positives": 0,
        "min_positive_cases": 3,
        "min_negative_cases": 1,
    }
