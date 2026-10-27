"""`_BUILTIN_ADAPTER_MODULES` is a hand-written list — this is its reconciler.

`craft/adapters/protocol.py` names the three modules whose import registers the
shipped adapters. That list cannot be derived at import time (importing it to
discover it is the very thing it is for), so it is hand-written — and a
hand-written list beside a directory of files drifts: add
`craft/adapters/rust_adapter.py` with an `ADAPTER_ID` and the registry quietly
stops seeing it, which is exactly the "registered but invisible" shape #482
fixed.

This gate reads the adapter modules with `ast` (no imports, no side effects) and
checks both directions:

* every class in `craft/adapters/*.py` that declares a string `ADAPTER_ID` must
  end up in `list_adapters()`;
* every module named in `_BUILTIN_ADAPTER_MODULES` must exist on disk.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import craft.adapters.protocol as proto

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADAPTERS_DIR = PROJECT_ROOT / "craft" / "adapters"


def _declared_adapter_ids() -> dict[str, str]:
    """``{adapter_id: "module.py:ClassName"}`` for every adapter in the folder.

    Read with `ast` on purpose: importing the modules would register them, and
    then the gate could not tell "the list is complete" from "the import did it".
    """
    declared: dict[str, str] = {}
    for path in sorted(ADAPTERS_DIR.glob("*.py")):
        if path.name in {"protocol.py", "__init__.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for stmt in node.body:
                targets: list[ast.expr] = []
                value: ast.expr | None = None
                if isinstance(stmt, ast.Assign):
                    targets = list(stmt.targets)
                    value = stmt.value
                elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                    targets = [stmt.target]
                    value = stmt.value
                if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                    continue
                if any(isinstance(t, ast.Name) and t.id == "ADAPTER_ID" for t in targets):
                    declared[value.value] = f"{path.name}:{node.name}"
    return declared


_DECLARED = _declared_adapter_ids()


def test_the_folder_actually_declares_some_adapters() -> None:
    """Anti-vacuity: an empty scan would make the reconciliation below trivially true."""
    assert _DECLARED, f"no class with a string ADAPTER_ID found in {ADAPTERS_DIR}"


@pytest.mark.parametrize(
    ("adapter_id", "where"),
    sorted(_DECLARED.items()),
    ids=[f"{where}->{adapter_id}" for adapter_id, where in sorted(_DECLARED.items())],
)
def test_every_declared_adapter_is_registered(adapter_id: str, where: str) -> None:
    """A new adapter file must also be named in `_BUILTIN_ADAPTER_MODULES`."""
    registered = {caps["adapter_id"] for caps in proto.list_adapters()}

    assert adapter_id in registered, (
        f"{where} declares ADAPTER_ID={adapter_id!r} but the registry does not "
        "have it — add its module to craft.adapters.protocol._BUILTIN_ADAPTER_MODULES"
    )


@pytest.mark.parametrize("module_name", proto._BUILTIN_ADAPTER_MODULES)
def test_every_listed_module_exists(module_name: str) -> None:
    """A stale entry in the list is a rename that was not followed."""
    module_path = PROJECT_ROOT / (module_name.replace(".", "/") + ".py")

    assert module_path.exists(), f"{module_name} is listed but {module_path} does not exist"


def test_the_list_names_every_adapter_module_on_disk() -> None:
    """The other direction: no adapter file may be silently absent from the list.

    `_DECLARED` maps each id to `module.py:ClassName`; the set of modules it
    mentions must be exactly what the list imports.
    """
    on_disk = {where.split(":")[0] for where in _DECLARED.values()}
    listed = {name.rsplit(".", 1)[-1] + ".py" for name in proto._BUILTIN_ADAPTER_MODULES}

    assert on_disk == listed
