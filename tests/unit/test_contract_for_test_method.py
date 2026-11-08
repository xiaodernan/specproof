"""Direct tests for ``_contract_for_test_method`` — the attribution table
that decides which contract a failing generated test is charged to.

Only two branches were pinned before (UNIQUE-01 via ``duplicate...``,
EVENT_ONCE-01 via ``RoutingKey``). The rest of the P6 families, the AUTH-01
fallback, and the precedence rules ("P6 families come first; the generic
UNIQUE-01 rule must not swallow the IDEMPOTENT method that contains the
substring 'duplicate'") were untested — they are the integrity of the
attribution path.
"""

from __future__ import annotations

import pytest

from agent.nodes.run_differential import _contract_for_test_method


@pytest.mark.parametrize(
    ("method", "contract"),
    [
        # P6 families — each exact method name maps to its family.
        ("listUsersMustNotUseNPlusOneQueries", "NPLUSONE-01"),
        ("getUserMustUseCacheAside", "CACHE-01"),
        ("emailChangeMustEvictUserCache", "CACHE-01"),
        ("staleStockWriteMustBeRejected", "CONCURRENCY-01"),
        ("duplicateOrderRequestMustBeDeduped", "IDEMPOTENT-01"),
        ("orderPlacementFailureMustNotLoseStock", "ATOMICITY-01"),
        ("cancelOrderMustRestock", "ATOMICITY-01"),
        ("fullStockOrderMustBeAllowed", "BOUNDARY-01"),
        ("orderAmountMustEqualUnitPriceTimesQuantity", "ORDER_AMOUNT-01"),
        ("orderCreatedEvent", "ORDER_EVENT-01"),
        ("orderRetry", "ORDER_EVENT-01"),
        ("invalidEmailChangeMustBeRejected", "EMAIL_FORMAT-01"),
        ("emailChangeMustNotPublishSpuriousEvent", "EVENT_ONCE-01"),
        ("emailChangeEventPayloadMustBeIntact", "EVENT_ONCE-01"),
        # Generic families reachable without a P6 hit.
        ("unauthenticatedRequestMustReturn401", "AUTH-01"),
        ("emailChangeEventMustGoToExpectedRoutingKey", "EVENT_ONCE-01"),
        ("emailChangeEventPayloadMustBeIntactCase", "EVENT_ONCE-01"),
        ("duplicateEmailChangeMustBeRejected", "UNIQUE-01"),
        ("freshEmailChangeMustSucceed", "UNIQUE-01"),
        ("blankEmailMustBeRejected", "UNIQUE-01"),
        # Nothing matches: AUTH-01 is the declared default.
        ("noop", "AUTH-01"),
    ],
)
def test_method_maps_to_contract(method: str, contract: str) -> None:
    assert _contract_for_test_method(method) == contract


def test_idempotent_method_with_duplicate_substring_is_not_swallowed() -> None:
    """The P6 IDEMPOTENT method starts with 'duplicate...' — the generic
    UNIQUE-01 substring rule must never claim it."""
    assert _contract_for_test_method("duplicateOrderRequestMustBeDeduped") == (
        "IDEMPOTENT-01"
    )


def test_order_event_methods_do_not_degrade_to_routing_key_path() -> None:
    """'orderCreatedEvent'/'orderRetry' are P6 ORDER_EVENT-01; neither may
    fall through to the RoutingKey/emailChangeEvent generic rule."""
    assert _contract_for_test_method("orderCreatedEvent") == "ORDER_EVENT-01"
    assert _contract_for_test_method("orderRetry") == "ORDER_EVENT-01"


def test_auth_default_is_the_exact_string_contract_name() -> None:
    assert _contract_for_test_method("") == "AUTH-01"
