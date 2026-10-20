"""Gates for the six experiment classes and the samples that stand for them.

The roadmap's Phase 3 exit condition is "每个新增契约族都有正样本、负样本、
holdout 和可重放 Capsule". `experiments/experiment_classes.py` is the
declaration; this file is the part that makes the declaration TRUE rather
than plausible.

What is checked, and why each one is a real failure mode:

* a named sample must EXIST — a registry that names a case nobody wrote
  is a promise the evaluation cannot keep;
* the positive sample's own ground truth must say "this must be caught"
  and name the SAME family — otherwise the registry's claim and the
  case's truth disagree, and one of them is wrong;
* the negative sample's ground truth must say "this must not be
  flagged" — a "negative" that is actually a positive is a false
  precision claim;
* the holdout must be declared in the holdout manifest, and must NOT
  be one of the cases the CI evaluates: the CI's subset has to stay
  non-holdout, or the "False positives: 0" gate there becomes vacuous
  (zero negative cases means zero false positives, always);
* a case cannot be both the tuning sample and the holdout;
* the template bodies and checker functions the registry names must
  EXIST in the modules that own them — a registry that names a
  template nobody wrote is decoration;
* the coverage report must match what the registry actually says, so
  the recorded gap (one family has no second case of its kind) cannot
  quietly become wrong.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from experiments.experiment_classes import (
    EXPERIMENT_CLASSES,
    MECHANISM_DIFFERENTIAL_TEST,
    MECHANISM_STATIC_CHECKER,
    ExperimentClass,
    by_family,
    sample_coverage,
)

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "golden-cases"
MANIFEST = REPO / "docs" / "eval" / "holdout-manifest.json"
CI = REPO / ".github" / "workflows" / "ci.yml"
TEMPLATES_MODULE = REPO / "agent" / "nodes" / "generate_counterexamples.py"
CHECKERS_MODULE = REPO / "agent" / "checkers" / "java_source.py"
COVERAGE_REPORT = REPO / "docs" / "eval" / "experiment-class-coverage.md"


def _truth(case_id: str) -> dict[str, Any]:
    path = GOLDEN / case_id / "ground-truth.json"
    assert path.is_file(), f"the sample {case_id!r} has no ground truth"
    return json.loads(path.read_text(encoding="utf-8"))


def _holdout_ids() -> set[str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {
        case["case_id"] for case in manifest["cases"]
        if case.get("status") in ("candidate", "active")
    }


def _ci_eval_subset() -> set[str]:
    """The cases the CI's own evaluation actually runs.

    Read out of the workflow file rather than a hand-typed list: the
    point of the check is that the CI's subset and the holdout set stay
    disjoint, and a list copied by hand is exactly how they would stop
    being disjoint.

    An EMPTY result is an error, not "no subset": the pattern not
    matching anything means the workflow changed its wording — and a
    gate that silently checks nothing is worse than no gate.
    """
    text = CI.read_text(encoding="utf-8")
    found = set(re.findall(r"golden-cases/([a-z0-9-]+)\s+eval-subset/", text))
    assert found, (
        "the CI evaluation subset could not be read from "
        f"{CI.name} — the pattern found no cases. Either the workflow "
        "changed its wording, or the subset is genuinely empty; both need "
        "a human, because a check that silently looks at nothing is not a "
        "check."
    )
    return found


ALL = list(EXPERIMENT_CLASSES)


@pytest.mark.parametrize("entry", ALL, ids=[e.key for e in ALL])
class TestTheRegistryIsTrue:
    def test_the_named_samples_exist(self, entry: ExperimentClass) -> None:
        for role, case_id in (
            ("positive", entry.positive_sample),
            ("negative", entry.negative_sample),
            ("holdout", entry.holdout_sample),
        ):
            if not case_id:
                continue
            assert (GOLDEN / case_id).is_dir(), (
                f"{entry.key}: the {role} sample {case_id!r} does not exist"
            )

    def test_the_positive_sample_agrees_with_the_registry(
        self, entry: ExperimentClass,
    ) -> None:
        truth = _truth(entry.positive_sample)
        assert truth.get("should_detect") is True, (
            f"{entry.key}: the positive sample {entry.positive_sample!r} says "
            f"should_detect={truth.get('should_detect')!r}"
        )
        assert truth.get("expected_contract") == entry.family, (
            f"{entry.key}: the positive sample expects contract "
            f"{truth.get('expected_contract')!r}, the registry says "
            f"{entry.family!r}"
        )

    def test_the_negative_sample_agrees_with_the_registry(
        self, entry: ExperimentClass,
    ) -> None:
        truth = _truth(entry.negative_sample)
        assert truth.get("should_detect") is False, (
            f"{entry.key}: the negative sample {entry.negative_sample!r} says "
            f"should_detect={truth.get('should_detect')!r} — a negative that "
            "is a positive is a false precision claim"
        )

    def test_the_holdout_is_declared_and_reserved(
        self, entry: ExperimentClass,
    ) -> None:
        if not entry.holdout_sample:
            return  # the gap is recorded by the coverage report
        assert entry.holdout_sample in _holdout_ids(), (
            f"{entry.key}: the holdout {entry.holdout_sample!r} is not declared "
            "in the holdout manifest — it would be tuned on, and then measured"
        )
        assert entry.holdout_sample not in _ci_eval_subset(), (
            f"{entry.key}: the holdout {entry.holdout_sample!r} is in the CI's "
            "own evaluation subset — the CI's 'False positives: 0' gate would "
            "become vacuous (zero negative cases means zero false positives)"
        )

    def test_the_holdout_is_not_the_tuning_sample(
        self, entry: ExperimentClass,
    ) -> None:
        if not entry.holdout_sample:
            return
        assert entry.holdout_sample != entry.positive_sample, (
            f"{entry.key}: one case cannot be both the tuning sample and the "
            "holdout"
        )

    def test_the_named_templates_exist(self, entry: ExperimentClass) -> None:
        source = TEMPLATES_MODULE.read_text(encoding="utf-8")
        for name in entry.templates:
            assert re.search(
                rf"^{re.escape(name)}\s*=", source, re.M
            ), f"{entry.key}: the template {name!r} does not exist"

    def test_the_named_checkers_exist(self, entry: ExperimentClass) -> None:
        source = CHECKERS_MODULE.read_text(encoding="utf-8")
        for name in entry.checkers:
            assert re.search(
                rf"^def {re.escape(name)}\(", source, re.M
            ), f"{entry.key}: the checker {name!r} does not exist"

    def test_the_mechanism_matches_what_the_registry_names(
        self, entry: ExperimentClass,
    ) -> None:
        if entry.mechanism == MECHANISM_DIFFERENTIAL_TEST:
            assert entry.templates, f"{entry.key}: no template named"
            assert not entry.checkers, (
                f"{entry.key}: a differential-test class names a checker too"
            )
        elif entry.mechanism == MECHANISM_STATIC_CHECKER:
            assert entry.checkers, f"{entry.key}: no checker named"
            assert not entry.templates, (
                f"{entry.key}: a static-checker class names a template too"
            )
        else:  # pragma: no cover — a new mechanism must be classified
            pytest.fail(f"{entry.key}: unknown mechanism {entry.mechanism!r}")


class TestTheRegistryItself:
    def test_the_six_named_classes_are_present(self) -> None:
        assert {entry.key for entry in EXPERIMENT_CLASSES} == {
            "transaction_rollback",
            "concurrency",
            "unique_constraint",
            "idempotency",
            "cache_consistency",
            "openapi_schema_diff",
        }

    def test_the_families_are_distinct(self) -> None:
        families = [entry.family for entry in EXPERIMENT_CLASSES]
        assert len(families) == len(set(families)), families

    def test_by_family_finds_the_class(self) -> None:
        for entry in EXPERIMENT_CLASSES:
            assert by_family(entry.family) is entry

    def test_every_class_says_what_it_does(self) -> None:
        for entry in EXPERIMENT_CLASSES:
            assert entry.subject.strip(), entry.key


class TestTheManifestVocabularyIsClosed:
    """The manifest must speak the same words as the cases it holds.

    It used to carry the legacy P6 group names (`authnz`, `transaction`,
    `uniqueness`, …) while the golden cases' ground truth and the
    registry speak CONTRACT FAMILY IDS. Two vocabularies in one file is
    how a case ends up in the wrong group — so the vocabulary is now
    closed, and this keeps it closed.
    """

    def test_every_declared_family_is_a_real_contract_family(self) -> None:
        known = self._contract_families()
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for case in manifest["cases"]:
            family = str(case.get("family") or "")
            assert family == "none" or family in known, (
                f"{case['case_id']}: the manifest declares family "
                f"{family!r}, which is not a contract family any golden case "
                f"expects. The vocabulary is: {sorted(known)} (or 'none')."
            )

    def test_a_manifest_family_matches_the_case_ground_truth(self) -> None:
        """The declared family must be the case's OWN family.

        A holdout declared under the wrong family would make the family's
        holdout count wrong — and the count is what an evaluation
        reports.
        """
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for case in manifest["cases"]:
            family = str(case.get("family") or "")
            if family == "none":
                continue
            truth = _truth(case["case_id"])
            assert truth.get("expected_contract") == family, (
                f"{case['case_id']}: the manifest says {family!r} but the "
                f"case's ground truth says "
                f"{truth.get('expected_contract')!r}"
            )

    def _contract_families(self) -> set[str]:
        families: set[str] = set()
        for case in sorted(GOLDEN.iterdir()):
            truth_path = case / "ground-truth.json"
            if not truth_path.is_file():
                continue
            truth = json.loads(truth_path.read_text(encoding="utf-8"))
            family = str(truth.get("expected_contract") or "")
            if family:
                families.add(family)
        assert families, "no golden case declares a contract family"
        return families


class TestTheCoverageReport:
    def test_the_report_exists(self) -> None:
        assert COVERAGE_REPORT.is_file(), (
            f"the coverage report {COVERAGE_REPORT} is missing — the gap it "
            "records has to be visible in the tree, not only in a test"
        )

    def test_the_ci_subset_is_readable(self) -> None:
        """The check above is only as good as what it reads.

        If the workflow's wording changes, the pattern finds nothing and
        the holdout-disjointness check would pass vacuously. So the
        read itself is asserted — a gate that looks at nothing must say
        so.
        """
        subset = _ci_eval_subset()
        assert len(subset) >= 2, subset
        for case_id in subset:
            assert (GOLDEN / case_id).is_dir(), (
                f"the CI evaluates {case_id!r}, which is not a golden case"
            )

    def test_the_report_matches_what_the_registry_says(self) -> None:
        """The recorded gap must not rot.

        A report that says "every class has all three samples" while the
        registry says otherwise is worse than no report: it would be
        quoted as coverage.
        """
        text = COVERAGE_REPORT.read_text(encoding="utf-8")
        coverage = sample_coverage()
        for key, missing in coverage.items():
            line = next(
                (
                    line for line in text.splitlines()
                    if line.strip().startswith(f"| {key} ")
                ),
                None,
            )
            assert line is not None, (
                f"the coverage report has no row for {key!r}; the registry "
                f"says its missing samples are {missing}"
            )
            for role in ("positive", "negative", "holdout"):
                present = "✅" if role not in missing else "—"
                assert present in line, (
                    f"the report's row for {key!r} does not mark {role} as "
                    f"{'present' if present == '✅' else 'missing'}"
                )
