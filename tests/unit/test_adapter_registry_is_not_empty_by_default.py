"""The adapter registry must never look empty — "no adapters" is not "no match".

Registration is an import side effect (`@register_adapter` runs when the adapter
module is imported), and **no production module imported the adapter modules**.
Measured in a fresh interpreter before the fix:

    >>> from craft.adapters.protocol import list_adapters, detect_adapter, get_adapter
    >>> list_adapters()
    []
    >>> detect_adapter(<a directory with go.mod>)
    None
    >>> get_adapter("go-test")
    AdapterNotImplemented: No adapter registered for go-test

`detect_adapter` returning ``None`` is a legitimate answer — "no adapter claims
this repository". But it was also the answer when the registry held nothing at
all, and those are different facts. That is the "skipped looks like passed"
shape this repo keeps fencing against, so the three registry entry points now
load the shipped adapters on first use.

The fresh-interpreter check runs in **one subprocess** (a new interpreter costs
seconds here): in-process, an earlier test has already imported the adapter
modules, so the defect is invisible.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import craft.adapters.protocol as proto

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_SHIPPED_IDS = {"java-gradle", "node-npm", "go-test"}

#: One interpreter, three answers, joined by ``|`` so a single assertion can
#: check them all: the registered ids, `get_adapter`, and `detect_adapter`.
_PROBE = """
import pathlib, tempfile
from craft.adapters.protocol import detect_adapter, get_adapter, list_adapters

ids = ",".join(sorted(a["adapter_id"] for a in list_adapters()))
by_id = get_adapter("go-test").ADAPTER_ID
with tempfile.TemporaryDirectory() as d:
    p = pathlib.Path(d)
    (p / "go.mod").write_text("module x\\ngo 1.21\\n", encoding="utf-8")
    found = detect_adapter(p)
print("|".join([ids, by_id, found.ADAPTER_ID if found else "NONE"]))
"""


@pytest.fixture(autouse=True)
def _restore_adapter_registry():
    """Snapshot/restore the global registry so this module leaves no trace."""
    saved = dict(proto._ADAPTER_REGISTRY)
    try:
        yield
    finally:
        proto._ADAPTER_REGISTRY.clear()
        proto._ADAPTER_REGISTRY.update(saved)


def test_a_fresh_interpreter_sees_the_shipped_adapters() -> None:
    """Importing *only* `protocol` must be enough to get a working registry.

    Three facts in one run, because they fail for the same reason:
    `list_adapters()` is non-empty, `get_adapter` resolves by id, and
    `detect_adapter` finds a Go project instead of answering ``None``.
    """
    env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT)}
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    assert completed.returncode == 0, f"stderr:\n{completed.stderr}"

    ids, by_id, detected = completed.stdout.strip().split("|")
    assert set(ids.split(",")) >= _SHIPPED_IDS
    assert by_id == "go-test"
    assert detected == "go-test"


def test_the_registry_reloads_after_someone_clears_it() -> None:
    """The load is re-entrant, not a one-shot import side effect.

    The registry fixtures in this suite snapshot and restore around every test;
    a restore that lands on a pre-load snapshot would otherwise leave the
    registry empty for the rest of the session.
    """
    proto._ADAPTER_REGISTRY.clear()

    ids = {caps["adapter_id"] for caps in proto.list_adapters()}

    assert ids >= _SHIPPED_IDS


def test_an_empty_registry_never_answers_none_for_a_claimed_project(tmp_path: Path) -> None:
    """The semantic point: empty registry ≠ no match."""
    (tmp_path / "go.mod").write_text("module x\ngo 1.21\n", encoding="utf-8")
    proto._ADAPTER_REGISTRY.clear()

    found = proto.detect_adapter(tmp_path)

    assert found is not None
    assert found.ADAPTER_ID == "go-test"
