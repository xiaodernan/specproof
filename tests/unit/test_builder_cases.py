"""Structural tests for the golden-scenario builder (SEG1 fix lane).

Pins the four constructions the segment-1 fixes depend on:

- case-25 (@Secured equivalence trap): the head must enable @Secured
  processing (@EnableMethodSecurity(securedEnabled = true)) because
  Spring Security 6.4 defaults securedEnabled=false and a bare
  @EnableMethodSecurity silently drops the guard (the observed AUTH-01
  false positive);
- case-30 (@Version moved to getter): the move must carry an explicit
  @Access(AccessType.PROPERTY) override, otherwise Hibernate's field
  access (the @Id sits on a field) ignores the getter-level @Version and
  optimistic locking disappears (the observed CONCURRENCY-01 false
  positive);
- case-31 (committed-before-validation): the REQUIRES_NEW decrement must
  live in a separate injected bean - a self-invoked helper bypasses the
  Spring transactional proxy and rolls back with the failed order, which
  is why the committed tag detected nothing (the observed ATOMICITY-01
  miss);
- case-09 (imperative block): the head mutations must be data-driven
  (CASE_09_MUTATIONS) so the committed tag carries BOTH the @PreAuthorize
  removal and the @Transactional removal - the pre-fix imperative helper
  edited the main tree and apply_case staged only the service file, so
  the committed case-09-head tag removed only @Transactional (the
  observed AUTH-01 miss).

No git, no network, no Docker: the builder module is loaded for its data
tables only.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, cast

_BUILDER_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "build_golden_scenarios.py"
)


def _load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_golden_scenarios", _BUILDER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _entry(module: ModuleType, case_id: str) -> dict[str, Any]:
    for entry in cast(list[dict[str, Any]], module.P6_CASES):
        if entry["case"] == case_id:
            return entry
    raise AssertionError(f"case not found in P6_CASES: {case_id}")


def _mutations(module: ModuleType, case_id: str) -> list[tuple[str, str, str]]:
    return cast(
        list[tuple[str, str, str]], list(_entry(module, case_id)["mutations"])
    )


def _added_files(module: ModuleType, case_id: str) -> list[tuple[str, str]]:
    return cast(
        list[tuple[str, str]], list(_entry(module, case_id)["added_files"])
    )


def test_case25_enables_secured_processing_in_head() -> None:
    module = _load_builder()
    security_hits = [
        (old, new)
        for rel, old, new in _mutations(module, "case-25")
        if rel == module.SECURITY
    ]
    assert security_hits, "case-25 must mutate the security config"
    _old, new = security_hits[0]
    assert "securedEnabled = true" in new, (
        "case-25 head must enable @Secured processing, got: " + new
    )
    annotation_hits = [
        new
        for rel, _old, new in _mutations(module, "case-25")
        if rel == module.CONTROLLER
        and '@Secured("IS_AUTHENTICATED_FULLY")' in new
    ]
    assert annotation_hits, (
        'case-25 must swap the guard to @Secured("IS_AUTHENTICATED_FULLY")'
    )
    import_hits = [
        new
        for rel, _old, new in _mutations(module, "case-25")
        if rel == module.CONTROLLER and "access.annotation.Secured" in new
    ]
    assert import_hits, (
        "case-25 must import the real Spring Security 6 package: "
        "org.springframework.security.access.annotation.Secured"
    )


def test_case30_version_getter_uses_property_access_override() -> None:
    module = _load_builder()
    import_hits = [
        new
        for rel, _old, new in _mutations(module, "case-30")
        if rel == module.PRODUCT_ENTITY
        and "jakarta.persistence.Access" in new
    ]
    assert import_hits, "case-30 must import the @Access annotation"
    removed = [m for m in _mutations(module, "case-30") if m[2] == ""]
    assert any("@Version" in old for _rel, old, _new in removed), (
        "case-30 must still remove @Version from the field"
    )
    getter_hits = [
        m for m in _mutations(module, "case-30")
        if "getVersion()" in m[1] and "@Version" in m[2]
    ]
    assert getter_hits, "case-30 must move @Version onto the getter"
    assert "@Access(AccessType.PROPERTY)" in getter_hits[0][2], (
        "getter-level @Version needs @Access(AccessType.PROPERTY) under "
        "Hibernate field access, got: " + getter_hits[0][2]
    )


def test_case31_decrement_uses_separate_bean_not_self_invocation() -> None:
    module = _load_builder()
    service_files = [
        content
        for rel, content in _added_files(module, "case-31")
        if rel.endswith("StockDeductionService.java")
    ]
    assert service_files, "case-31 must add a StockDeductionService bean"
    source = service_files[0]
    assert "REQUIRES_NEW" in source
    assert "@Transactional" in source

    order_hits = {
        new
        for rel, _old, new in _mutations(module, "case-31")
        if rel == module.ORDER_SERVICE
    }
    joined = "\n".join(sorted(order_hits))
    assert "stockDeductionService.decrement(" in joined, (
        "case-31 must decrement through the injected bean"
    )
    assert "StockDeductionService stockDeductionService" in joined, (
        "case-31 must inject the deduction bean into OrderService"
    )
    assert "decrementStockInNewTransaction" not in joined, (
        "case-31 must not use a self-invoked helper (proxy bypass)"
    )


def test_case09_mutations_are_data_driven_and_remove_both_annotations() -> None:
    module = _load_builder()
    # The head-v1 (flagship) build still uses the imperative helper - its
    # commit_and_tag() stages the whole demo/ subtree, so the edit lands
    # there. Case 09 must NOT depend on that path: its mutations must be
    # a data table so apply_case_detached commits them all.
    assert hasattr(module, "CASE_09_MUTATIONS"), (
        "case-09 must be data-driven (CASE_09_MUTATIONS)"
    )
    muts = module.CASE_09_MUTATIONS
    controller_hits = [
        (old, new)
        for rel, old, new in muts
        if rel == module.CONTROLLER
    ]
    service_hits = [
        (old, new)
        for rel, old, new in muts
        if rel == module.SERVICE
    ]
    assert controller_hits, "case-09 must mutate the controller"
    assert any(
        "PreAuthorize" in old and new == "" for old, new in controller_hits
    ), "case-09 must remove the @PreAuthorize import"
    assert any(
        "@PreAuthorize" in old and new == "" for old, new in controller_hits
    ), "case-09 must remove the @PreAuthorize guard annotation"
    assert service_hits, "case-09 must mutate the service"
    assert any(
        "@Transactional" in old and new == "" for old, new in service_hits
    ), "case-09 must remove @Transactional"
