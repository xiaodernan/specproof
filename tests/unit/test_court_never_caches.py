"""Court lanes must never replay from a cache.

Written as a regression lock for the 2026-11-16 audit: the policy-layer and
the provider-layer both hold the same invariant — `cacheable()` accepts only
`draft | diagnose`, the in-memory store hard-refuses evidence kinds even when
enabled, and rejection is counted (not silently swallowed).
"""

from providers.semantic_cache import SemanticCache, cacheable


def test_cacheable_accepts_only_draft_and_diagnose() -> None:
    for kind in ["court", "counterexample", "accept_judge", "contract_compile", "edit_plan", "", "   ", "COURT", "Accept_Judge"]:
        assert cacheable(kind) is False, kind


def test_cacheable_is_case_and_whitespace_insensitive() -> None:
    assert cacheable("draft") is True
    assert cacheable("  Diagnose ") is True
    assert cacheable("DIAGNOSE") is True


def test_semantic_cache_put_hard_refuses_court_kinds() -> None:
    cache = SemanticCache(enabled=True)
    assert cache.put("k", {"verdict": "VERIFIED"}, kind="court") is False
    assert cache.put("k2", "accept", kind="accept_judge") is False
    assert cache.get("k") is None
    assert cache.get("k2") is None
    assert cache.size == 0
    assert cache.rejected == 2
    assert cache.puts == 0


def test_semantic_cache_disabled_false_clears() -> None:
    cache = SemanticCache(enabled=True)
    assert cache.put("ok", "draft-value", kind="draft") is True
    assert cache.size == 1
    assert cache.get("ok") == "draft-value"
    cache.clear()
    assert cache.size == 0
