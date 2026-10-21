"""The key family a contract is about — derived, not guessed.

A contract says which family of keys it is about ("session tokens ...
invalidated in Redis"); the PROFILE says what that family is called in
this domain ("token:user:"). The ids inside the family belong to the
domain, so the family is SCANNED, never listed by hand.

These tests pin:
- the family comes from the contract's own text;
- the ADDRESS comes from the profile (so a different domain gets its
  own names);
- a contract that names no family gets NOTHING observed (guessing
  would be inventing evidence);
- the scan reads the keys the family actually contains.
"""

from __future__ import annotations

from typing import Any

from agent.experiments.profile import DEMO_PROFILE, TemplateProfile
from experiments.collectors import RedisStateCollector
from experiments.external_state import key_patterns_for


def _contract(**overrides: Any) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "id": "TOKEN-01",
        "checker_type": "redis",
        "requirement": (
            "when a user changes their email, all existing session tokens "
            "for that user must be invalidated in Redis"
        ),
    }
    contract.update(overrides)
    return contract


def test_the_family_comes_from_the_contract_text() -> None:
    assert key_patterns_for(_contract()) == ["token:user:*"]


def test_a_cache_contract_gets_the_cache_family() -> None:
    contract = _contract(
        id="CACHE-01",
        requirement="the cached user entry must be evicted on write",
    )
    assert key_patterns_for(contract) == ["user:cache:*"]


def test_a_contract_that_names_no_family_gets_nothing() -> None:
    """Nothing named ⇒ nothing observed. Guessing would invent evidence."""
    contract = _contract(
        requirement="unauthenticated requests must receive 401",
    )
    assert key_patterns_for(contract) == []


def test_the_address_comes_from_the_profile() -> None:
    """A different domain gets its own key names — the same words."""
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
        cancel_order_path='"/api/orders/cancel"',
        user_detail_path='"/api/users/" + "{id}"',
        user_cache_key="shopper:cache:",
        user_token_key="shopper:token:",
    )
    assert key_patterns_for(_contract(), other) == ["shopper:token:*"]
    # And the demo's own names are not in there.
    assert key_patterns_for(_contract(), other)[0] != "token:user:*"


def test_the_demo_profile_is_the_default() -> None:
    assert key_patterns_for(_contract()) == key_patterns_for(
        _contract(), DEMO_PROFILE
    )


# ── the scan ───────────────────────────────────────────────────────────────


class _ScanningRedis:
    """A Redis double that can enumerate a family."""

    def __init__(self, keys: dict[str, str] | None = None) -> None:
        self.keys = keys or {}
        self.scanned: list[str] = []

    def get(self, name: str) -> Any:
        return self.keys.get(name)

    def ttl(self, name: str) -> int:
        return 60 if name in self.keys else -2

    def scan_iter(self, match: str | None = None, count: int | None = None) -> Any:
        import fnmatch

        self.scanned.append(match or "")
        return [
            key for key in self.keys
            if match is None or fnmatch.fnmatch(key, match)
        ]


def test_the_scan_reads_the_keys_the_family_contains() -> None:
    client = _ScanningRedis({"token:user:7": "abc", "other:key": "x"})
    collector = RedisStateCollector(client)

    states = collector.snapshot_by_pattern(["token:user:*"])

    assert set(states) == {"token:user:7"}
    assert states["token:user:7"].present is True
    assert states["token:user:7"].value == "abc"
    assert client.scanned == ["token:user:*"]


def test_a_client_that_cannot_scan_observes_nothing() -> None:
    """An unscanable family is UNSEEN — not "the family is empty"."""

    class _NoScan:
        def get(self, name: str) -> Any:
            return None

        def ttl(self, name: str) -> int:
            return -2

    collector = RedisStateCollector(_NoScan())
    assert collector.snapshot_by_pattern(["token:user:*"]) == {}


def test_a_scan_that_fails_observes_nothing() -> None:
    class _BrokenScan:
        def get(self, name: str) -> Any:
            return None

        def ttl(self, name: str) -> int:
            return -2

        def scan_iter(self, match: str | None = None, count: int | None = None) -> Any:
            raise RuntimeError("redis down")

    collector = RedisStateCollector(_BrokenScan())
    assert collector.snapshot_by_pattern(["token:user:*"]) == {}
