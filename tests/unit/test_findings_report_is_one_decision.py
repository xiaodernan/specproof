"""Two scanners, one emptiness rule.

``evidence/orphan_scan.py`` walks the LOCAL payload directory;
``evidence/bucket_reconcile.py`` walks the buckets and the index. Both
answer the same operator question — "is anything broken in this evidence
chain?" — and they must answer it with the same rule. If the two
drifted, the same chain could be "clean" to one scanner and "broken" to
the other, and nobody would be able to say which one to believe.

The rule lives in ``evidence/findings_report.py`` (one implementation).
These legs pin that: both report classes inherit the SAME function
object, and both answer "clean" the same way for the same inputs.
"""

from __future__ import annotations

from evidence.bucket_reconcile import BucketFinding, BucketReconcileReport
from evidence.findings_report import FindingsReport
from evidence.orphan_scan import ObjectFinding, ObjectScanReport


def test_both_report_kinds_share_the_one_is_clean_implementation() -> None:
    assert ObjectScanReport.is_clean is FindingsReport.is_clean
    assert BucketReconcileReport.is_clean is FindingsReport.is_clean


def test_an_empty_report_is_clean_in_both_vocabularies() -> None:
    assert ObjectScanReport().is_clean() is True
    assert BucketReconcileReport().is_clean() is True


def test_a_report_with_a_finding_is_not_clean_in_both_vocabularies() -> None:
    scan = ObjectScanReport(
        findings=[
            ObjectFinding(
                kind="orphan",
                object_id="obj-1",
                path="capsules/x.zip",
                detail="no index row",
            )
        ]
    )
    reconcile = BucketReconcileReport(
        findings=[
            BucketFinding(
                kind="unindexed",
                bucket="specproof-bug-capsules",
                object_name="jobs/x/capsule.zip",
                detail="no index row",
            )
        ]
    )

    assert scan.is_clean() is False
    assert reconcile.is_clean() is False


def test_the_shared_base_is_the_one_that_decides() -> None:
    """A subclass that overrode the rule would break the shared decision.

    The base class is where the answer lives; neither report kind is
    allowed to answer it on its own.
    """
    assert "is_clean" not in BucketReconcileReport.__dict__
    assert "is_clean" not in ObjectScanReport.__dict__
