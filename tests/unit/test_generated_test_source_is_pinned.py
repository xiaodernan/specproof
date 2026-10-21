"""The generated experiment source must not change by accident.

The generated JUnit source is what the pipeline actually runs against a
repository, so a change in it is a change in what SpecProof proves. It
used to be invisible: the templates lived as strings in a node module,
and nothing pinned the source they produce.

Now the templates are profile-driven (the domain NAMES come from
`agent/experiments/profile.py`), and this file pins the RESULT: the
source the demo profile produces must equal the golden snapshot
byte-for-byte. A change in a template, in the profile, or in the
assembly shows up here as a diff — and the diff is the point.

The golden was produced by rendering the PRE-profile templates and the
POST-profile ones from the same contract set and comparing them: they
were identical, so the refactor was a refactor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent.experiments.profile import DEMO_PROFILE, TemplateProfile
from agent.nodes.generate_counterexamples import _build_deterministic_test

REPO = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).resolve().parent / "golden" / "generated_test_demo.java"

#: One contract per family the templates dispatch on — the set that
#: exercises every branch of the assembly.
CONTRACTS: list[dict[str, Any]] = [
    {"id": "AUTH-01", "expected_behavior": "unauthenticated must 401"},
    {"id": "UNIQUE-01", "expected_behavior": "duplicate email must be rejected"},
    {"id": "EVENT_ONCE-01", "expected_behavior": "event published once"},
    {"id": "CACHE-01", "expected_behavior": "cache evicted on write"},
    {"id": "CONCURRENCY-01", "expected_behavior": "stale write rejected"},
    {"id": "IDEMPOTENT-01", "expected_behavior": "duplicate request deduped"},
    {"id": "ATOMICITY-01", "expected_behavior": "failed order keeps stock"},
    {"id": "BOUNDARY-01", "expected_behavior": "stock boundary enforced"},
    {"id": "ORDER_AMOUNT-01", "expected_behavior": "amount not inflated"},
    {"id": "NPLUSONE-01", "expected_behavior": "no per-user loop"},
    {"id": "ORDER_EVENT-01", "expected_behavior": "order event published"},
    {"id": "EMAIL_FORMAT-01", "expected_behavior": "email format validated"},
]


def test_the_golden_exists() -> None:
    assert GOLDEN.is_file(), (
        f"{GOLDEN} is missing — the generated source has no pinned snapshot"
    )


def test_the_demo_profile_reproduces_the_golden() -> None:
    source = _build_deterministic_test([dict(c) for c in CONTRACTS])
    golden = GOLDEN.read_text(encoding="utf-8")
    assert source == golden, (
        "the generated experiment source changed. That is a change in what "
        "SpecProof proves — read the diff, and if it is intended, update the "
        "golden in the same commit (and say why in the commit message)."
    )


class TestTheProfile:
    def test_no_placeholder_survives_the_render(self) -> None:
        """An undeclared placeholder would reach the generated Java."""
        source = _build_deterministic_test([dict(c) for c in CONTRACTS])
        assert "@@" not in source, (
            "the generated source still contains a placeholder: "
            f"{source[source.find('@@'):source.find('@@') + 60]!r}"
        )

    def test_a_different_profile_changes_the_names_only(self) -> None:
        """The point of the profile: the domain NAMES are parameterised.

        The LOGIC (what the test asserts) stays the same — that is the
        honest limit of this layer, and the test says so by checking the
        assertions survived.
        """
        other = TemplateProfile(
            java_package="com.example.shop",
            user="Shopper",
            user_repo="shopperRepository",
            product="Item",
            product_repo="itemRepository",
            order="Purchase",
            order_repo="purchaseRepository",
            user_repo_class="ShopperRepository",
            product_repo_class="ItemRepository",
            order_repo_class="PurchaseRepository",
            place_order_request="PlacePurchaseRequest",
            cancel_order_request="CancelPurchaseRequest",
            change_email_request="ChangeEmailRequest",
            order_event="PurchaseCreatedEvent",
            sql_query_counter="SqlQueryCounter",
            sql_query_counter_field="sqlQueryCounter",
            email_event="EmailChangedEvent",
            test_config_class="TestMockBeansConfig",
            place_order_path='"/api/purchases"',
            user_email_path='"/api/users/" + "{id}" + "/email"',
            cancel_order_path='"/api/purchases/cancel"',
            user_detail_path='"/api/users/" + "{id}"',
            user_cache_key="user:cache:",
            user_token_key="token:user:",
        )
        source = _build_deterministic_test(
            [dict(c) for c in CONTRACTS], other
        )
        assert "com.example.shop" in source
        assert "PlacePurchaseRequest" in source
        # The CLASS names follow the profile; the LOCAL variable names are
        # part of the template's logic (a product/order template names its
        # locals product/user) — that boundary is the honest limit of this
        # layer.
        assert "Item product = new Item(" in source
        assert "Shopper user = new Shopper(" in source
        # The logic is unchanged: the same assertions, in the same places.
        assert "Stale write was silently accepted" in source
        assert "Failed order leaked its stock decrement" in source
        # And the demo's names are gone.
        assert "com.specproof.demo" not in source
        assert "PlaceOrderRequest" not in source

    def test_the_demo_profile_is_the_one_in_use(self) -> None:
        """The node must render with the demo profile today."""
        from agent.nodes import generate_counterexamples as gen_module

        assert gen_module.DEMO_PROFILE is DEMO_PROFILE


@pytest.mark.parametrize("contract_id", [c["id"] for c in CONTRACTS])
def test_each_family_reaches_the_source(contract_id: str) -> None:
    """Every dispatched family must actually appear in the source.

    A family whose template silently stopped being selected would leave
    the contract UNVERIFIED at run time — and the reader would see
    "the experiment did not run" instead of "the experiment found
    something".
    """
    source = _build_deterministic_test(
        [{"id": contract_id, "expected_behavior": "x"}]
    )
    assert "@@" not in source
    assert "void " in source, contract_id


def test_the_concurrency_family_carries_both_spellings() -> None:
    """The repository-level AND the service-path stale read.

    The repository-level template drives the repository, so it can only
    see defects that live in an entity annotation. The service-path one
    drives the order flow against a stale read, so it can also see a
    defect in the service's own write path. One spelling of the family
    would leave it able to hold only one kind of defect, and the second
    kind would be invisible rather than absent.
    """
    source = _build_deterministic_test(
        [{"id": "CONCURRENCY-01", "expected_behavior": "x"}]
    )
    assert "void staleStockWriteMustBeRejected()" in source
    assert "void concurrentStockDecrementMustNotLoseTheOtherWritersChange()" in source


def test_the_service_path_template_still_injects_a_stale_read() -> None:
    """The seam must be IN the generated source, not only in the template.

    A template that lost its seam would still compile and would still
    pass — it would just stop testing anything. The seam is the whole
    point, so its presence is pinned.
    """
    source = _build_deterministic_test(
        [{"id": "CONCURRENCY-01", "expected_behavior": "x"}]
    )
    assert "StaleProductReadConfig" in source
    assert '"findById".equals(method.getName())' in source
    assert "StaleProductReadConfig.stale = stale" in source
    # And it must be DISARMED before the row is read back, or the
    # assertion would read the snapshot it planted instead of the
    # database.
    assert "StaleProductReadConfig.stale = null" in source
