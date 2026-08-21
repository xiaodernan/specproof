"""Deterministic compilation of spec/spec.md — the SpecProof-verdict stand-in.

check_module(source) executes a (possibly mutated) pricing module and probes
the spec'd behaviors. Any deviation, crash, or missing symbol is a contract
violation. Deliberately no probes for the advisory tip behavior, which the
spec marks out of scope (mutant M06 must survive).
"""

from __future__ import annotations

from typing import Any


def _exec_module(source: str) -> tuple[dict[str, Any], str]:
    namespace: dict[str, Any] = {}
    try:
        exec(compile(source, "<pricing>", "exec"), namespace)  # noqa: S102
    except Exception as exc:  # noqa: BLE001
        return {}, f"module failed to execute: {type(exc).__name__}: {exc}"
    return namespace, ""


#: (label, function, args, expected result) — the spec's executable probes.
_PROBES: list[tuple[str, str, tuple[object, ...], object]] = [
    ("bulk discount at exact threshold (C1)", "apply_bulk_discount", (500.0,), 450.0),
    ("bulk discount above threshold (C1)", "apply_bulk_discount", (600.0,), 540.0),
    ("free shipping at exact threshold (C2)", "is_free_shipping", (100.0,), True),
    ("free shipping below threshold (C2)", "is_free_shipping", (50.0,), False),
    ("tax rate is 8% (C3)", "with_tax", (100.0,), 108.0),
]


def check_module(source: str) -> list[str]:
    """Return contract violations for a (possibly mutated) pricing module."""
    namespace, load_error = _exec_module(source)
    if load_error:
        return [load_error]
    violations: list[str] = []
    for label, func_name, args, expected in _PROBES:
        func: Any = namespace.get(func_name)
        if not callable(func):
            violations.append(f"{func_name} missing or not callable")
            continue
        try:
            actual: Any = func(*args)
        except Exception as exc:  # noqa: BLE001
            violations.append(f"{label}: raised {type(exc).__name__}: {exc}")
            continue
        if actual != expected:
            violations.append(f"{label}: expected {expected!r}, got {actual!r}")
    return violations
