"""The six dynamic experiment classes, as a reusable protocol (P3-4).

The roadmap's Phase 3 exit condition is: "每个新增契约族都有正样本、负样本、
holdout 和可重放 Capsule" — every contract family that gets a new
experiment class must carry a positive sample, a negative sample, a
holdout and a replayable capsule.

This module is the reusable half of that declaration: ONE entry per
experiment class, naming

* the contract **family** it covers — so the checker, the template and
  the sample all speak the same word;
* the **mechanism** that detects it (a generated differential test, or a
  static checker);
* the golden **cases** that stand for it — a POSITIVE (must be caught),
  a NEGATIVE (must not be flagged) and a HOLDOUT (reserved for
  evaluation);
* the template bodies / checker functions that implement it.

Every sample is a REAL golden case, and the ground truth inside each
case is what the registry asserts — so an entry that drifts from the
case it names is caught by a gate, not by a reader's trust.

The templates each class names are **profile-driven** (the domain
NAMES come from `agent/experiments/profile.py`, not from the template
text), and the source they produce is pinned byte-for-byte by
`tests/unit/test_generated_test_source_is_pinned.py` — so a template
edit shows up as a diff in the generated Java, which is what the
pipeline actually runs.

The holdout is the one that can be MISSING, and that is recorded
rather than faked: ``holdout_sample`` is ``None`` when the family has
no second case of its own kind, and :func:`sample_coverage` says so
out loud instead of the gap disappearing into a default.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The mechanism that detects an experiment class. Two kinds exist, and
#: the difference is not cosmetic: a generated differential test EXECUTES
#: the behaviour, a static checker can only read the source.
MECHANISM_DIFFERENTIAL_TEST = "generated_differential_test"
MECHANISM_STATIC_CHECKER = "static_checker"


@dataclass(frozen=True)
class ExperimentClass:
    """One experiment class and the samples that stand for it."""

    #: Stable key (the registry's own vocabulary).
    key: str
    #: The contract family this class covers (AUTH-01, ATOMICITY-01, …).
    family: str
    #: What the experiment does, in one line — the reader's map.
    subject: str
    #: How the class is detected.
    mechanism: str
    #: The template bodies (module-level names) that implement it, in the
    #: module that owns them. Empty for a static-checker class.
    templates: tuple[str, ...] = ()
    #: The checker functions (module-level names) that implement it, in the
    #: module that owns them. Empty for a differential-test class.
    checkers: tuple[str, ...] = ()
    #: A golden case that MUST be caught (a positive sample).
    positive_sample: str = ""
    #: A golden case that must NOT be flagged (a negative sample).
    negative_sample: str = ""
    #: A golden case reserved for evaluation (a holdout). Empty when the
    #: family has no second case of its own kind — a gap, recorded.
    holdout_sample: str = ""

    def missing_samples(self) -> tuple[str, ...]:
        """Which of the three samples this class does not have."""
        missing: list[str] = []
        if not self.positive_sample:
            missing.append("positive")
        if not self.negative_sample:
            missing.append("negative")
        if not self.holdout_sample:
            missing.append("holdout")
        return tuple(missing)


#: The six classes the roadmap names for Phase 3: 事务回滚 / 并发 / 唯一约束 /
#: 幂等 / 缓存一致性 / OpenAPI schema diff.
EXPERIMENT_CLASSES: tuple[ExperimentClass, ...] = (
    ExperimentClass(
        key="transaction_rollback",
        family="ATOMICITY-01",
        subject="一次失败的多写操作必须整体回滚，不留半截状态",
        mechanism=MECHANISM_DIFFERENTIAL_TEST,
        templates=("_ROLLBACK_TEST_TEMPLATE", "_CANCEL_RESTOCK_TEST_TEMPLATE"),
        positive_sample="case-31-tx-decrement-committed-before-validation",
        negative_sample="case-34-tx-equivalent-dedup-lookup",
        holdout_sample="case-39-tx-cancel-no-restock",
    ),
    ExperimentClass(
        key="concurrency",
        family="CONCURRENCY-01",
        subject="同一行的并发写必须有一方失败，不得静默覆盖",
        mechanism=MECHANISM_DIFFERENTIAL_TEST,
        templates=(
            "_STALE_STOCK_TEST_TEMPLATE",
            "_SERVICE_STALE_STOCK_TEST_TEMPLATE",
        ),
        positive_sample="case-29-tx-optimistic-lock-removed",
        negative_sample="case-30-tx-version-guard-moved-to-getter",
        # The GAP is closed (#334): the family now has a SECOND case of
        # its own kind, and a case cannot be both the tuning sample and
        # the holdout.
        #
        # case-101 is a SERVICE-level defect, not a second spelling of
        # case-29: the stock decrement is written by a bulk UPDATE that
        # carries no version predicate, so the service writes back the
        # value it read and the other writer's decrement is lost. The
        # repository-level template cannot see it — the repository is
        # never asked to do the write. Measured on the demo: the base
        # passes (18/18) and the mutant fails with "the other writer's
        # stock (5) must survive, got 7", while the other 17 generated
        # tests still pass on that mutant.
        holdout_sample="case-101-tx-bulk-update-bypasses-version-guard",
    ),
    ExperimentClass(
        key="unique_constraint",
        family="UNIQUE-01",
        subject="重复的实体必须被拒绝，重复写入不得静默通过",
        mechanism=MECHANISM_DIFFERENTIAL_TEST,
        templates=(
            "_UNIQUE_TEST_TEMPLATE", "_FRESH_TEST_TEMPLATE",
            "_BLANK_TEST_TEMPLATE",
        ),
        positive_sample="case-19-email-corruption",
        negative_sample="case-78-logic-email-input-trimmed",
        holdout_sample="case-04-duplicate-email",
    ),
    ExperimentClass(
        key="idempotency",
        family="IDEMPOTENT-01",
        subject="同一请求重复投递只能生效一次",
        mechanism=MECHANISM_DIFFERENTIAL_TEST,
        templates=("_IDEMPOTENT_TEST_TEMPLATE",),
        positive_sample="case-33-tx-order-idempotency-dedup-removed",
        negative_sample="case-36-tx-new-order-lookup-endpoint",
        holdout_sample="case-35-tx-stock-decrement-off-by-one",
    ),
    ExperimentClass(
        key="cache_consistency",
        family="CACHE-01",
        subject="写入必须失效缓存，缓存不得比库更旧",
        mechanism=MECHANISM_DIFFERENTIAL_TEST,
        templates=("_CACHE_EVICT_TEST_TEMPLATE", "_CACHE_ASIDE_TEST_TEMPLATE"),
        positive_sample="case-57-redis-cache-ttl-removed",
        negative_sample="case-59-redis-cache-helpers-extracted",
        holdout_sample="case-58-redis-cache-writeback-removed",
    ),
    ExperimentClass(
        key="openapi_schema_diff",
        family="BACKWARD_COMPATIBLE-01",
        subject="对外契约不得破坏：删字段、改路径、改动词都是破坏",
        mechanism=MECHANISM_STATIC_CHECKER,
        checkers=("check_schema_compat",),
        positive_sample="case-53-api-order-count-field-removed",
        negative_sample="case-52-api-new-product-detail-endpoint",
        holdout_sample="case-06-schema-break",
    ),
)


def by_family(family: str) -> ExperimentClass | None:
    """The class covering a contract family, if there is one."""
    for entry in EXPERIMENT_CLASSES:
        if entry.family == family:
            return entry
    return None


def sample_coverage() -> dict[str, tuple[str, ...]]:
    """Which samples each class has — the honest coverage picture.

    A class missing a holdout is not a failure of the registry; it is a
    gap in the SAMPLE POOL, and this is where it is said out loud.
    """
    return {
        entry.key: entry.missing_samples() for entry in EXPERIMENT_CLASSES
    }


__all__ = [
    "EXPERIMENT_CLASSES",
    "MECHANISM_DIFFERENTIAL_TEST",
    "MECHANISM_STATIC_CHECKER",
    "ExperimentClass",
    "by_family",
    "sample_coverage",
]
