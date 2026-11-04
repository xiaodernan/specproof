"""Regression tests for the detection-core fixes (B1/B2/B3/B4 in DESIGN_REVIEW).

These tests lock in the behaviours that were broken:
  B1: annotation splitting must keep @PreAuthorize("isAuthenticated()")
      (nested parens) so AUTH-01 is detected
  B4: token-invalidation detection is call-site based (method-level)
  B2: contract_results merge semantics (FAIL beats PASS, no data loss)
  B3: run_differential emits source-diff evidence even without a test
"""

from agent.checkers.java_source import (
    _implemented_interface_names,
    _split_with_annotations,
    check_token_invalidation,
    contract_results_for,
    run_contract_checks,
)
from agent.contract_results import merge_contract_results
from agent.worker import _terminal_status_from_state

BASE_CONTROLLER = """package com.specproof.demo.controller;

@RestController
@RequestMapping("/api/users")
public class UserController {

    @PutMapping("/{id}/email")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<UserResponse> changeEmail(
            @PathVariable Long id,
            @Valid @RequestBody ChangeEmailRequest request) {
        return ResponseEntity.ok(userService.changeEmail(id, request));
    }
}
"""

ANNOTATION_LINE = "    @PreAuthorize(\"isAuthenticated()\")"
HEAD_CONTROLLER = BASE_CONTROLLER.replace(ANNOTATION_LINE + chr(10), "")


def test_splitter_keeps_nested_paren_annotation():
    """B1: @PreAuthorize("isAuthenticated()") must stay attached to its method."""
    blocks = {
        name: block for block, name in _split_with_annotations(BASE_CONTROLLER)
    }
    assert "changeEmail" in blocks
    assert "@PreAuthorize" in blocks["changeEmail"]
    assert "@PutMapping" in blocks["changeEmail"]


def test_auth_removal_detected_with_nested_paren_annotation():
    """B1: the flagship base->head regression must produce AUTH-01."""
    rel = "com/specproof/demo/controller/UserController.java"
    findings = run_contract_checks({rel: BASE_CONTROLLER}, {rel: HEAD_CONTROLLER})
    auth = [f for f in findings if f["contract_id"] == "AUTH-01"]
    assert len(auth) == 1
    assert auth[0]["type"] == "annotation_removed"
    assert auth[0]["severity"] == "MAJOR"


def test_composed_custom_annotation_counts_as_protection():
    """case-13: @RequireAuth (composed custom security annotation) replaces
    @PreAuthorize — equivalent protection, must NOT be a finding."""
    rel = "com/specproof/demo/controller/UserController.java"
    head = BASE_CONTROLLER.replace(
        '    @PreAuthorize("isAuthenticated()")\n',
        "    @RequireAuth\n",
    )
    findings = run_contract_checks({rel: BASE_CONTROLLER}, {rel: head})
    auth = [f for f in findings if f["contract_id"] == "AUTH-01"]
    assert auth == []


def test_interface_default_method_annotation_counts_as_protection():
    """case-14: @PreAuthorize moved to an implemented interface's default
    method — Spring resolves interface-level method security, so the
    endpoint stays protected and no finding may be emitted."""
    rel = "com/specproof/demo/controller/UserController.java"
    iface_rel = "com/specproof/demo/controller/UserApi.java"
    head_controller = BASE_CONTROLLER.replace(
        '    @PreAuthorize("isAuthenticated()")\n', "",
    ).replace(
        "public class UserController {",
        "public class UserController implements UserApi {",
    )
    head_interface = """package com.specproof.demo.controller;

public interface UserApi {

    @PreAuthorize("isAuthenticated()")
    default void changeEmail() {}
}
"""
    findings = run_contract_checks(
        {rel: BASE_CONTROLLER},
        {rel: head_controller, iface_rel: head_interface},
    )
    auth = [f for f in findings if f["contract_id"] == "AUTH-01"]
    assert auth == []


def test_implements_clause_parsing():
    assert _implemented_interface_names(
        "public class UserController implements UserApi {"
    ) == ["UserApi"]
    assert _implemented_interface_names(
        "public class X implements A, B {"
    ) == ["A", "B"]
    assert _implemented_interface_names("public class X {") == []


BASE_SERVICE = """@Service
public class UserService {
    @Transactional
    public UserResponse changeEmail(Long userId, ChangeEmailRequest request) {
        userRepository.save(user);
        invalidateOldTokens(userId);
        rabbitTemplate.convertAndSend("specproof.demo.events", event);
        return new UserResponse(user.getId(), user.getUsername(), user.getEmail());
    }

    private void invalidateOldTokens(Long userId) {
        redisTemplate.delete("token:user:" + userId);
    }
}
"""

HEAD_SERVICE_CALL_REMOVED = """@Service
public class UserService {
    @Transactional
    public UserResponse changeEmail(Long userId, ChangeEmailRequest request) {
        userRepository.save(user);
        rabbitTemplate.convertAndSend("specproof.demo.events", event);
        return new UserResponse(user.getId(), user.getUsername(), user.getEmail());
    }

    private void invalidateOldTokens(Long userId) {
        redisTemplate.delete("token:user:" + userId);
    }
}
"""


def test_token_call_removed_but_method_kept_is_detected():
    """B4: removing only the CALL must still be detected (case-05)."""
    rel = "com/specproof/demo/service/UserService.java"
    findings = check_token_invalidation(
        {rel: BASE_SERVICE}, {rel: HEAD_SERVICE_CALL_REMOVED}
    )
    assert len(findings) == 1
    assert findings[0]["contract_id"] == "TOKEN_INVALIDATION-01"
    assert "changeEmail" in findings[0]["description"]


def test_token_call_intact_no_false_positive():
    """B4: identical service must produce no token finding."""
    rel = "com/specproof/demo/service/UserService.java"
    findings = check_token_invalidation({rel: BASE_SERVICE}, {rel: BASE_SERVICE})
    assert findings == []


def test_merge_contract_results_fail_beats_pass():
    """B2: a FAIL from one experiment must beat a PASS from another."""
    merged = merge_contract_results(
        [{"contract_id": "AUTH-01", "result": "PASS", "experiment": "static"}],
        [{"contract_id": "AUTH-01", "result": "FAIL", "experiment": "differential"}],
    )
    assert merged == [
        {"contract_id": "AUTH-01", "result": "FAIL", "experiment": "differential"}
    ]


def test_merge_contract_results_keeps_other_contracts():
    """B2: merging must never drop results for other contracts."""
    merged = merge_contract_results(
        [
            {"contract_id": "AUTH-01", "result": "PASS"},
            {"contract_id": "TRANSACTION-01", "result": "PASS"},
        ],
        [{"contract_id": "AUTH-01", "result": "FAIL"}],
    )
    by_id = {r["contract_id"]: r["result"] for r in merged}
    assert by_id["AUTH-01"] == "FAIL"
    assert by_id["TRANSACTION-01"] == "PASS"


def test_terminal_status_mapping():
    """B11: worker terminal status reflects the real pipeline result."""
    assert _terminal_status_from_state({"errors": ["boom"]}) == "FAILED"
    assert _terminal_status_from_state(
        {"errors": [], "confirmed_findings": [{"severity": "BLOCKER"}]}
    ) == "BLOCKED"
    # A row that carries no verdict and no contract id: the evidence is
    # missing (NEEDS_REVIEW), and the declared unverified count does not
    # match the rows (a contradiction), so the word is BLOCKED — the two
    # records disagree about what was measured.
    assert _terminal_status_from_state(
        {"errors": [], "confirmed_findings": [], "matrix": {"unverified": 1, "rows": [{}]}}
    ) == "BLOCKED"
    assert _terminal_status_from_state(
        {"errors": [], "confirmed_findings": [], "matrix": {"unverified": 0, "passed": 1,
         "rows": [{"contract_id": "C-1", "result": "PASS", "experiment": "check",
                   "evidence": "e-1"}]}}
    ) == "VERIFIED"


def test_contract_results_for_fail_when_checker_finds_violation():
    """contract_results_for: findings → FAIL result with evidence ref."""
    contracts = [{"id": "AUTH-01"}]
    findings = [{"contract_id": "AUTH-01", "type": "annotation_removed",
                 "id": "finding-1", "description": "@PreAuthorize removed"}]
    base_files = {"com/specproof/demo/controller/UserController.java":
                  "class UserController {}"}
    results = contract_results_for(contracts, findings, base_files)
    assert results == [{"contract_id": "AUTH-01", "result": "FAIL",
                        "experiment": "java_source_diff",
                        "evidence_ref": "finding-1",
                        "details": "@PreAuthorize removed"}]


def test_contract_results_for_pass_when_guarded_construct_intact():
    """contract_results_for: no findings + observed base → PASS."""
    contracts = [{"id": "AUTH-01"}]
    findings = []
    base_file = ("public class UserController {\n"
                 "    @PutMapping(\"/{id}/email\")\n"
                 "    @PreAuthorize(\"isAuthenticated()\")\n"
                 "    public void changeEmail() {}\n}")
    base_files = {"com/specproof/demo/controller/UserController.java": base_file}
    results = contract_results_for(contracts, findings, base_files)
    assert results == [{"contract_id": "AUTH-01", "result": "PASS",
                        "experiment": "java_source_diff",
                        "evidence_ref": "no violation found in source diff",
                        "details": "Checker ran; guarded construct intact in Head"}]


def test_contract_results_for_unverified_when_not_observed():
    """contract_results_for: no findings + not observed → UNVERIFIED."""
    contracts = [{"id": "AUTH-01"}]
    findings = []
    base_files = {"com/specproof/demo/controller/UserController.java":
                  "class UserController {}"}
    results = contract_results_for(contracts, findings, base_files)
    assert results == [{"contract_id": "AUTH-01", "result": "UNVERIFIED",
                        "experiment": "java_source_diff",
                        "evidence_ref": None,
                        "details": "No observable construct for this contract in Base"}]


def test_contract_results_for_unverified_when_checker_failed():
    """contract_results_for: checker crashed → UNVERIFIED with CHECKER_FAILED ref."""
    contracts = [{"id": "AUTH-01"}]
    findings = [{"contract_id": "OTHER-01", "type": "checker_failed",
                 "id": "cf-1", "families": ["AUTH-01"],
                 "description": "checker crashed"}]
    base_files = {"com/specproof/demo/controller/UserController.java":
                  "class UserController {}"}
    results = contract_results_for(contracts, findings, base_files)
    assert results == [{"contract_id": "AUTH-01", "result": "UNVERIFIED",
                        "experiment": "java_source_diff",
                        "evidence_ref": "CHECKER_FAILED",
                        "details": "checker for this contract family crashed — "
                                   "never PASS by silence"}]
