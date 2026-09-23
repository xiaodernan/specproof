"""#53 (roadmap Phase 1.5): the `slow` marker auto-tagging must actually work.

The conftest ``pytest_collection_modifyitems`` hook auto-tags a measured set of
slow unit modules so contributors can run ``-m 'not integration and not slow'``
for a fast inner loop. This locks three things offline:

  * a known-slow module's tests really carry the ``slow`` marker;
  * a known-fast module's tests do NOT (the tag is selective, not blanket);
  * the marker is registered (``--strict-markers`` would otherwise error), so the
    deselect expression is honored rather than silently ignored.

The check runs ``pytest --collect-only`` in a subprocess because the marker is
applied by the collection hook (not a decorator on the function object), so it is
only observable through real collection.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _collected_slow(node_ids: list[str]) -> list[str]:
    """Return the node ids that ``-m slow`` selects under a strict-marker run."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        # The repo's ini addopts carry `-v`, which cancels a command-line `-q`
        # and makes --collect-only print a tree instead of node ids. Clear it so
        # the probe reads the same selection a contributor would deselect.
        "-o",
        "addopts=",
        *node_ids,
        "-m",
        "slow",
        "--strict-markers",
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    proc = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=180
    )
    # 5 = nothing selected, which is the expected outcome for a fast module.
    assert proc.returncode in (0, 5), proc.stdout + proc.stderr
    return [ln for ln in proc.stdout.splitlines() if "::" in ln]


def test_known_slow_module_is_tagged_slow() -> None:
    ids = _collected_slow(["tests/unit/test_agent_runtime.py"])
    assert ids, "a measured-slow module must expose slow-tagged collected tests"
    assert all("test_agent_runtime.py" in nid for nid in ids)


def test_known_fast_module_is_not_tagged_slow() -> None:
    # test_baseline is real unit coverage but NOT in the slow set, so the
    # selective tag must not sweep it in — otherwise the fast loop lies.
    ids = _collected_slow(["tests/unit/test_baseline.py"])
    assert ids == []
