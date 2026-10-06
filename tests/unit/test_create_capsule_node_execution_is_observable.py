"""Capsule-packing node execution tests (#200) — honest counters at the
node boundary, written WITH the landing (not backfilled).

The object-metadata recorder is stubbed (best-effort side path); the
capsule files, the zip packaging and the replay scripts are written for
real into a tmp cwd (the node's capsules directory is relative to the
process cwd). One case per outcome word in CREATE_CAPSULE_OUTCOMES:

- packed: a BLOCKER finding (with a MINOR sibling that must be filtered
  out) yields exactly one capsule zip with its full payload, and the
  metadata recorder is invoked once;
- no_findings: an empty confirmed-findings list yields an empty capsules
  list;
- filtered_out: findings that exist but sit below the BLOCKER/MAJOR
  threshold yield the same empty list — the word is the countable
  difference;

plus create_capsule_runs_total on every path and a drift gate binding the
parity family's regex words to CREATE_CAPSULE_OUTCOMES and to the source
literals.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

import pytest

from agent.nodes.create_capsule import (
    CREATE_CAPSULE_OUTCOMES,
    create_capsule_node,
)
from observability.metrics import snapshot

ROOT = Path(__file__).resolve().parents[2]

# Derived from the declaration — a new word extends the delta table.
_COUNTERS = ("create_capsule_runs_total",) + tuple(
    f"create_capsule_outcomes_{word}_total"
    for word in sorted(CREATE_CAPSULE_OUTCOMES)
)


def _counter(name: str) -> float:
    # The registry stores BARE names — the specproof_ prefix is added by
    # render_text only.
    return snapshot()["counters"].get(name, 0.0)


def _before() -> dict[str, float]:
    return {name: _counter(name) for name in _COUNTERS}


def _deltas(before: dict[str, float]) -> dict[str, float]:
    return {name: _counter(name) - start for name, start in before.items()}


def _only(*words: str) -> dict[str, float]:
    """Expected deltas: runs+1 and exactly the named outcome words +1."""
    deltas = dict.fromkeys(_COUNTERS, 0.0)
    deltas["create_capsule_runs_total"] = 1.0
    for word in words:
        deltas[f"create_capsule_outcomes_{word}_total"] = 1.0
    return deltas


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


def _stub_metadata(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    recorder = _Recorder()
    monkeypatch.setattr(
        "storage.object_metadata.record_file_object_best_effort", recorder
    )
    return recorder


def _state(tmp_path: Path, findings: list[dict[str, Any]]) -> dict[str, Any]:
    tests = tmp_path / "SpecProofGeneratedTest.java"
    tests.write_text("class SpecProofGeneratedTest {}", encoding="utf-8")
    return {
        "confirmed_findings": findings,
        "contracts": [{"id": "AUTH-01", "checker_type": "http"}],
        "requirement_text": "Unauthenticated requests must receive 401.",
        "generated_tests_path": str(tests),
        "base_ref": "base",
        "head_ref": "head-v1",
        "job_id": "job-200",
    }


def test_packed_counts_packed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    recorder = _stub_metadata(monkeypatch)
    findings = [
        {
            "id": "F1",
            "severity": "BLOCKER",
            "confidence": 0.9,
            "contract_id": "AUTH-01",
            "description": "guard removed",
        },
        {"id": "F2", "severity": "MINOR", "contract_id": "AUTH-01"},
    ]
    before = _before()
    out = create_capsule_node(_state(tmp_path, findings))  # type: ignore[arg-type]

    assert len(out["capsules"]) == 1
    zip_path = Path(out["capsules"][0])
    assert zip_path.is_file()
    assert zip_path.name == "capsule-F1.zip", (
        "the MINOR sibling must be filtered out of the packaging"
    )

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "finding.json" in names
        assert "run.sh" in names
        assert "run.ps1" in names
        assert "README.md" in names
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["finding_id"] == "F1"
    assert manifest["manifest_digest"].startswith("sha256:")

    assert len(recorder.calls) == 1
    (args, kwargs) = recorder.calls[0]
    assert args[0] == "capsule"
    assert kwargs["job_id"] == "job-200"
    assert kwargs["contract_ids"] == ("AUTH-01",)
    assert _deltas(before) == _only("packed")


def test_no_findings_counts_no_findings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    before = _before()
    out = create_capsule_node(_state(tmp_path, []))  # type: ignore[arg-type]

    assert out["capsules"] == []
    assert _deltas(before) == _only("no_findings")


def test_filtered_out_counts_filtered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    findings = [{"id": "F3", "severity": "MINOR", "contract_id": "AUTH-01"}]
    before = _before()
    out = create_capsule_node(_state(tmp_path, findings))  # type: ignore[arg-type]

    assert out["capsules"] == [], (
        "below-threshold findings produce the same empty list as none at all"
    )
    assert _deltas(before) == _only("filtered_out")


def test_outcome_vocabulary_matches_parity_and_source() -> None:
    from tests.unit.test_observability_metric_parity import CONCATENATED_FAMILIES

    source = (ROOT / "agent" / "nodes" / "create_capsule.py").read_text(
        encoding="utf-8"
    )
    literals = set(
        re.findall(
            r'incr\("create_capsule_outcomes_([a-z0-9_]+)_total"\)', source
        )
    )
    assert literals == set(CREATE_CAPSULE_OUTCOMES), (
        f"source literals {sorted(literals)} != declared vocabulary "
        f"{sorted(CREATE_CAPSULE_OUTCOMES)}"
    )
    assert source.count('incr("create_capsule_runs_total")') == 1

    pattern, _ = CONCATENATED_FAMILIES["create_capsule"]
    parity_words = set(
        re.search(r"\(([^()]+)\)", pattern.pattern).group(1).split("|")  # type: ignore[union-attr]
    )
    assert parity_words == set(CREATE_CAPSULE_OUTCOMES), (
        f"parity family words {sorted(parity_words)} != declared vocabulary "
        f"{sorted(CREATE_CAPSULE_OUTCOMES)}"
    )
