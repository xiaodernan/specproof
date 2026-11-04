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
    check_endpoint_changes,
    check_event_once,
    check_schema_compat,
    check_token_invalidation,
    check_unique_email,
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


def test_contract_results_for_migration_and_test_strength():
    """contract_results_for: base_schema_present/base_test_present → MIGRATION-01
    and TEST_STRENGTH-01 get PASS without any findings or source analysis."""
    contracts = [
        {"id": "MIGRATION-01"},
        {"id": "TEST_STRENGTH-01"},
    ]
    findings = []
    base_files = {}
    results = contract_results_for(contracts, findings, base_files,
                                   base_schema_present=True,
                                   base_test_present=True)
    assert results == [
        {"contract_id": "MIGRATION-01", "result": "PASS",
         "experiment": "java_source_diff",
         "evidence_ref": "no violation found in source diff",
         "details": "Checker ran; guarded construct intact in Head"},
        {"contract_id": "TEST_STRENGTH-01", "result": "PASS",
         "experiment": "java_source_diff",
         "evidence_ref": "no violation found in source diff",
         "details": "Checker ran; guarded construct intact in Head"},
    ]


def test_contract_results_for_migration_and_test_strength_not_present():
    """contract_results_for: base_schema_present/base_test_present=False →
    MIGRATION-01 and TEST_STRENGTH-01 get UNVERIFIED."""
    contracts = [
        {"id": "MIGRATION-01"},
        {"id": "TEST_STRENGTH-01"},
    ]
    findings = []
    base_files = {}
    results = contract_results_for(contracts, findings, base_files,
                                   base_schema_present=False,
                                   base_test_present=False)
    assert results == [
        {"contract_id": "MIGRATION-01", "result": "UNVERIFIED",
         "experiment": "java_source_diff",
         "evidence_ref": None,
         "details": "No observable construct for this contract in Base"},
        {"contract_id": "TEST_STRENGTH-01", "result": "UNVERIFIED",
         "experiment": "java_source_diff",
         "evidence_ref": None,
         "details": "No observable construct for this contract in Base"},
    ]


def test_contract_results_for_multiple_findings_joined() -> None:
    """contract_results_for: 同一合同多个发现，details 用 "; " 连接。"""
    contracts = [{"id": "AUTH-01"}]
    findings = [
        {"contract_id": "AUTH-01", "type": "annotation_removed",
         "id": "f-1", "description": "@PreAuthorize removed"},
        {"contract_id": "AUTH-01", "type": "annotation_removed",
         "id": "f-2", "description": "@Secured removed"},
    ]
    base_files = {"com/specproof/demo/controller/UserController.java":
                  "class UserController {}"}
    results = contract_results_for(contracts, findings, base_files)
    assert results == [{"contract_id": "AUTH-01", "result": "FAIL",
                        "experiment": "java_source_diff",
                        "evidence_ref": "f-1",
                        "details": "@PreAuthorize removed; @Secured removed"}]


def test_contract_results_for_migration_true_test_false() -> None:
    """contract_results_for: base_schema_present=True, base_test_present=False →
    MIGRATION-01 PASS，TEST_STRENGTH-01 UNVERIFIED。"""
    contracts = [
        {"id": "MIGRATION-01"},
        {"id": "TEST_STRENGTH-01"},
    ]
    findings = []
    base_files = {}
    results = contract_results_for(contracts, findings, base_files,
                                   base_schema_present=True,
                                   base_test_present=False)
    assert results == [
        {"contract_id": "MIGRATION-01", "result": "PASS",
         "experiment": "java_source_diff",
         "evidence_ref": "no violation found in source diff",
         "details": "Checker ran; guarded construct intact in Head"},
        {"contract_id": "TEST_STRENGTH-01", "result": "UNVERIFIED",
         "experiment": "java_source_diff",
         "evidence_ref": None,
         "details": "No observable construct for this contract in Base"},
    ]


def test_contract_results_for_migration_false_test_true() -> None:
    """contract_results_for: base_schema_present=False, base_test_present=True →
    MIGRATION-01 UNVERIFIED，TEST_STRENGTH-01 PASS。"""
    contracts = [
        {"id": "MIGRATION-01"},
        {"id": "TEST_STRENGTH-01"},
    ]
    findings = []
    base_files = {}
    results = contract_results_for(contracts, findings, base_files,
                                   base_schema_present=False,
                                   base_test_present=True)
    assert results == [
        {"contract_id": "MIGRATION-01", "result": "UNVERIFIED",
         "experiment": "java_source_diff",
         "evidence_ref": None,
         "details": "No observable construct for this contract in Base"},
        {"contract_id": "TEST_STRENGTH-01", "result": "PASS",
         "experiment": "java_source_diff",
         "evidence_ref": "no violation found in source diff",
         "details": "Checker ran; guarded construct intact in Head"},
    ]


def test_contract_results_for_mixed_findings() -> None:
    """contract_results_for: 同一批合同，部分有发现，部分无结果。"""
    contracts = [
        {"id": "AUTH-01"},
        {"id": "TXN-01"},
    ]
    findings = [
        {"contract_id": "AUTH-01", "type": "annotation_removed",
         "id": "f-1", "description": "@PreAuthorize removed"},
    ]
    base_files = {"com/specproof/demo/controller/UserController.java":
                  "class UserController {}"}
    results = contract_results_for(contracts, findings, base_files)
    assert results == [
        {"contract_id": "AUTH-01", "result": "FAIL",
         "experiment": "java_source_diff",
         "evidence_ref": "f-1",
         "details": "@PreAuthorize removed"},
        {"contract_id": "TXN-01", "result": "UNVERIFIED",
         "experiment": "java_source_diff",
         "evidence_ref": None,
         "details": "No observable construct for this contract in Base"},
    ]



def test_endpoint_changes_removal_is_detected() -> None:
    """check_endpoint_changes: removing an @PutMapping endpoint is OPENAPI-01."""
    base_files = {
        "com/specproof/demo/controller/UserController.java": BASE_CONTROLLER,
    }
    # Head removes the @PutMapping("/{id}/email") endpoint
    head = BASE_CONTROLLER.replace(
        """    @PutMapping("/{id}/email")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<UserResponse> changeEmail(""",
        """    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<UserResponse> changeEmail(""",
    )
    head_files = {
        "com/specproof/demo/controller/UserController.java": head,
    }
    findings = check_endpoint_changes(base_files, head_files)
    removals = [f for f in findings if f["contract_id"] == "OPENAPI-01"]
    assert len(removals) == 1
    assert removals[0]["type"] == "endpoint_removed"
    assert "/{id}/email" in removals[0]["description"]


def test_endpoint_changes_unchanged_surface_is_clean() -> None:
    """check_endpoint_changes: same endpoints on Base and Head → no findings."""
    base_files = {
        "com/specproof/demo/controller/UserController.java": BASE_CONTROLLER,
    }
    head_files = {
        "com/specproof/demo/controller/UserController.java": BASE_CONTROLLER,
    }
    findings = check_endpoint_changes(base_files, head_files)
    assert findings == []

def test_schema_compat_removed_field_is_detected() -> None:
    """check_schema_compat: removing a DTO field is BACKWARD_COMPATIBLE-01."""
    base_files = {
        "com/specproof/demo/dto/UserDto.java": (
            "package com.speproject.demo.dto;\n"
            "public class UserDto {\n"
            "    private String email;\n"
            "    private String name;\n"
            "}\n"
        ),
    }
    head_files = {
        "com/specproof/demo/dto/UserDto.java": (
            "package com.speproject.demo.dto;\n"
            "public class UserDto {\n"
            "    private String name;\n"
            "}\n"
        ),
    }
    findings = check_schema_compat(base_files, head_files)
    removals = [f for f in findings if f["contract_id"] == "BACKWARD_COMPATIBLE-01"]
    assert len(removals) == 1
    assert removals[0]["type"] == "schema_break"
    assert "email" in removals[0]["description"]


def test_schema_compat_unchanged_fields_is_clean() -> None:
    """check_schema_compat: same fields on Base and Head → no findings."""
    dto = (
        "package com.speproject.demo.dto;\n"
        "public class UserDto {\n"
        "    private String email;\n"
        "    private String name;\n"
        "}\n"
    )
    base_files = {
        "com/specproof/demo/dto/UserDto.java": dto,
    }
    head_files = {
        "com/specproof/demo/dto/UserDto.java": dto,
    }
    findings = check_schema_compat(base_files, head_files)
    assert findings == []


def test_unique_email_guard_removed_is_detected() -> None:
    """check_unique_email: removing existsByEmail guard is UNIQUE-01."""
    base_files = {
        "com/specproof/demo/repository/UserRepository.java": (
            "public interface UserRepository extends JpaRepository<User, Long> {\n"
            "    Optional<User> existsByEmail(String email);\n"
            "}\n"
        ),
    }
    head_files = {
        "com/specproof/demo/repository/UserRepository.java": (
            "public interface UserRepository extends JpaRepository<User, Long> {\n"
            "}\n"
        ),
    }
    findings = check_unique_email(base_files, head_files)
    removals = [f for f in findings if f["contract_id"] == "UNIQUE-01"]
    assert len(removals) == 1
    assert removals[0]["type"] == "guard_removed"
    assert "existsByEmail" in removals[0]["description"]


def test_unique_email_guard_unchanged_is_clean() -> None:
    """check_unique_email: two ends both have existsByEmail → no findings."""
    repo_if = (
        "public interface UserRepository extends JpaRepository<User, Long> {\n"
        "    Optional<User> existsByEmail(String email);\n"
        "}\n"
    )
    base_files = {
        "com/specproof/demo/repository/UserRepository.java": repo_if,
    }
    head_files = {
        "com/specproof/demo/repository/UserRepository.java": repo_if,
    }
    findings = check_unique_email(base_files, head_files)
    assert findings == []


def test_token_invalidation_guard_removed_is_detected() -> None:
    """check_token_invalidation: removing invalidateOldTokens call is TOKEN_INVALIDATION-01."""
    base_files = {
        "com/specproof/demo/service/UserService.java": (
            "public class UserService {\n"
            "    private void invalidateOldTokens(Long userId) {\n"
            "        redisTemplate.delete(\"token:user:\" + userId);\n"
            "    }\n"
            "}\n"
        ),
    }
    head_files = {
        "com/specproof/demo/service/UserService.java": (
            "public class UserService {\n"
            "    private void invalidateOldTokens(Long userId) {\n"
            "    }\n"
            "}\n"
        ),
    }
    findings = check_token_invalidation(base_files, head_files)
    removals = [f for f in findings if f["contract_id"] == "TOKEN_INVALIDATION-01"]
    assert len(removals) == 1
    assert removals[0]["type"] == "guard_removed"
    assert "invalidateOldTokens" in removals[0]["description"]


def test_token_invalidation_guard_unchanged_is_clean() -> None:
    """check_token_invalidation: both ends have invalidateOldTokens call → no findings."""
    svc = (
        "public class UserService {\n"
        "    private void invalidateOldTokens(Long userId) {\n"
        "        redisTemplate.delete(\"token:user:\" + userId);\n"
        "    }\n"
        "}\n"
    )
    base_files = {
        "com/specproof/demo/service/UserService.java": svc,
    }
    head_files = {
        "com/specproof/demo/service/UserService.java": svc,
    }
    findings = check_token_invalidation(base_files, head_files)
    assert findings == []


def test_event_once_increased_publish_is_detected() -> None:
    """check_event_once: convertAndSend 调用次数增加是 EVENT_ONCE-01."""
    base_files = {
        "com/specproof/demo/service/EventService.java": (
            "public class EventService {\n"
            "    public void sendEvent() {\n"
            "        rabbitTemplate.convertAndSend(\"exchange\", \"event\");\n"
            "    }\n"
            "}\n"
        ),
    }
    head_files = {
        "com/specproof/demo/service/EventService.java": (
            "public class EventService {\n"
            "    public void sendEvent() {\n"
            "        rabbitTemplate.convertAndSend(\"exchange\", \"event1\");\n"
            "        rabbitTemplate.convertAndSend(\"exchange\", \"event2\");\n"
            "    }\n"
            "}\n"
        ),
    }
    findings = check_event_once(base_files, head_files)
    removals = [f for f in findings if f["contract_id"] == "EVENT_ONCE-01"]
    assert len(removals) == 1
    assert removals[0]["type"] == "duplicate_publish"
    assert "1 -> 2" in removals[0]["description"]


def test_event_once_unchanged_is_clean() -> None:
    """check_event_once: convertAndSend 调用次数不变 → 无发现."""
    svc = (
        "public class EventService {\n"
        "    public void sendEvent() {\n"
        "        rabbitTemplate.convertAndSend(\"exchange\", \"event\");\n"
        "    }\n"
        "}\n"
    )
    base_files = {
        "com/specproof/demo/service/EventService.java": svc,
    }
    head_files = {
        "com/specproof/demo/service/EventService.java": svc,
    }
    findings = check_event_once(base_files, head_files)
    assert findings == []
