"""The renew-lease fake must stay in lockstep with the production Lua script.

#2071 added a ``_FakeRedis.eval`` to the worker-recovery integration test that
MODELS ``storage.redis._RENEW_LEASE_LUA`` by hand: owner check, max-hold window
check, then EXPIRE. A hand-written model drifts silently — if production adds
or removes a branch, the fake keeps answering for the OLD script and the test
stays green on a model that no longer matches reality.

This gate reads the production script's structure and pins that the three
decision points the fake implements are still the three the script has. It does
not re-implement Lua (no Redis here): it asserts the source-level contract that
makes the fake's answers meaningful. If a branch is added/removed in
_RENEW_LEASE_LUA, one of these legs goes red and forces the fake to be updated.
"""

from __future__ import annotations

import re

from storage.redis import _RENEW_LEASE_LUA


def _script() -> str:
    return _RENEW_LEASE_LUA


def test_script_is_the_named_renew_lease_contract() -> None:
    assert "specproof:renew-lease" in _script()


def test_owner_check_uses_get_keys1_argv1() -> None:
    # GET KEYS[1] ~= ARGV[1] -> return 0 : the fake's `store[keys[0]] != argv[0]`
    assert re.search(r"GET',\s*KEYS\[1\].*ARGV\[1\]", _script()), _script()


def test_cap_window_check_uses_exists_keys2_and_keys3() -> None:
    # EXISTS KEYS[2] == 1 AND EXISTS KEYS[3] == 0 -> return 0 : the fake's
    # `keys[1] in store and keys[2] not in store`
    assert "EXISTS', KEYS[2]" in _script()
    assert "EXISTS', KEYS[3]" in _script()


def test_success_branch_expires_keys1_with_argv2_then_returns_1() -> None:
    # EXPIRE KEYS[1] ARGV[2] ; return 1 : the fake's `expired.append((keys[0], int(argv[1])))`
    assert "EXPIRE', KEYS[1], ARGV[2]" in _script()
    assert re.search(r"return\s+1", _script())


def test_script_has_exactly_two_zero_branches_and_one_one_branch() -> None:
    # Pin the decision shape: two `return 0` (owner mismatch, cap window closed)
    # and one `return 1` (renewed). A new branch added to production must make
    # this red so the fake is revisited.
    zeros = len(re.findall(r"return\s+0", _script()))
    ones = len(re.findall(r"return\s+1", _script()))
    assert zeros == 2, f"expected 2 denial branches, script has {zeros}"
    assert ones == 1, f"expected 1 success branch, script has {ones}"
