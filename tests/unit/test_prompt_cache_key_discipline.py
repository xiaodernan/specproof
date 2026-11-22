"""One sticky cache key per lane, or the gateway shards never hold steady.

Pinned here, once and for all:

* every ``prompt_cache_key`` / ``cache_key`` literal in ``api/`` and
  ``craft/`` is lowercase ``specproof-<kebab>`` and under 64 chars;
* the sticky-lane registry is EXACT: every registered lane is present, and no
  tenth key appears without this file being updated on purpose;
* the review court (``agent/review_court``) never carries a
  ``prompt_cache_key`` — ever;
* ``scripts/lane_cache_probe.py`` documents the full lane registry
  and no longer hard-codes a stale model name in the evidence payload.

If this file fails, the drift was deliberate or accidental — either way it
must not ship silently; the cache discipline is the whole point of the
bible sandwich.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

KEY_RE = re.compile(r"specproof-[a-z0-9][a-z0-9-]{2,62}")
_CANONICAL_LINES = re.compile(r"(prompt_cache_key|cache_key)")

EXPECTED_KEYS = {
    "specproof-observe-advice",
    "specproof-insight-advice",
    "specproof-ai-summary",
    "specproof-dig",
    "specproof-runbook",
    "specproof-worldbook-ask",
    "specproof-exhibit-copilot",
    "specproof-next-step-advice",
    "specproof-stress-digest",
    # The model-driven routing lane (product face of the model_router graph).
    # Its own sticky key keeps the routed two-call prefix warm and separate
    # from the other lanes — one key per lane is the parallel-session contract.
    "specproof-model-router",
}


def _sticky_keys(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        if not _CANONICAL_LINES.search(line):
            continue
        out.extend(KEY_RE.findall(line))
    return out


def _collect() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for root in (REPO / "api", REPO / "craft"):
        for path in sorted(root.rglob("*.py")):
            keys = _sticky_keys(path.read_text(encoding="utf-8"))
            if keys:
                found[str(path.relative_to(REPO))] = keys
    return found


def test_sticky_keys_are_well_formed() -> None:
    for rel, keys in _collect().items():
        for key in keys:
            assert KEY_RE.fullmatch(key), f"{rel}: ill-formed key {key!r}"
            assert len(key) <= 63, f"{rel}: {key!r} over 63 chars"


def test_the_lane_registry_is_exact() -> None:
    seen = {key for keys in _collect().values() for key in keys}
    missing = EXPECTED_KEYS - seen
    extra = seen - EXPECTED_KEYS
    assert not missing, f"lanes lost their sticky key: {sorted(missing)}"
    assert not extra, f"unregistered sticky key in the tree: {sorted(extra)}"


def test_each_lane_key_is_unique_outside_its_home() -> None:
    # the dig key legitimately appears twice in craft/investigators.py
    # (two default args); across files the registered keys must be pairwise unshared
    owning: dict[str, list[str]] = {}
    for rel, keys in _collect().items():
        for key in keys:
            owning.setdefault(key, []).append(rel)
    for key in EXPECTED_KEYS:
        files = set(owning.get(key, []))
        assert files, f"{key} disappeared from the tree"
        assert len(files) <= 1, f"{key} shared across files: {sorted(files)}"


def test_the_review_court_never_carries_a_cache_key() -> None:
    court = REPO / "agent" / "review_court"
    sources = list(court.rglob("*.py"))
    assert sources, "review_court tree missing — test is blind"
    for path in sources:
        assert "prompt_cache_key" not in path.read_text(encoding="utf-8"), (
            f"{path.relative_to(REPO)} carries a cache key — court must never cache"
        )


def test_lane_cache_probe_registers_all_lanes() -> None:
    probe = (REPO / "scripts" / "lane_cache_probe.py").read_text(encoding="utf-8")
    for key in EXPECTED_KEYS:
        assert key in probe, f"probe registry lost {key}"
    assert "gpt-6.1-terra" not in probe, "probe hard-coded the retired model again"


def test_lane_cache_probe_reads_model_from_config() -> None:
    probe = (REPO / "scripts" / "lane_cache_probe.py").read_text(encoding="utf-8")
    assert "load_model_config" in probe
