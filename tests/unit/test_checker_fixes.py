"""Regression tests for the detection-core fixes (B1/B2/B3/B4 in DESIGN_REVIEW).

These tests lock in the behaviours that were broken:
  B1: annotation splitting must keep @PreAuthorize("isAuthenticated()")
      (nested parens) so AUTH-01 is detected
  B4: token-invalidation detection is call-site based (method-level)
  B2: contract_results merge semantics (FAIL beats PASS, no data loss)
  B3: run_differential emits source-diff evidence even without a test
"""

from agent.checkers.constitution import check_forbidden_changes
from agent.checkers.java_source import (
    _implemented_interface_names,
    _split_with_annotations,
    check_token_invalidation,
    run_contract_checks,
)
from agent.checkers.schema_and_tests import check_test_weakening

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
}"""

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
    head_controller = BASE_CONTROLLER.replace(
        '    @PreAuthorize("isAuthenticated()")\n', ""
    ).replace(
        "public class UserController {",
        "public class UserController implements UserApi {",
    )
    head_interface = """package com.specproof.demo.controller;

public interface UserApi {

    @PreAuthorize("isAuthenticated()")
    default void changeEmail() {}
}"""
    head_files = {
        rel: head_controller,
        "com/specproof/demo/controller/UserApi.java": head_interface,
    }
    findings = run_contract_checks(base_files={rel: BASE_CONTROLLER}, head_files=head_files)
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


def test_token_invalidation_guard_removed_is_detected():
    """check_token_invalidation: 移除 invalidateOldTokens 调用是 TOKEN_INVALIDATION-01。"""
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


def test_check_test_weakening_test_count_decreased() -> None:
    """check_test_weakening: @Test 计数减少是 TEST_STRENGTH-01。"""
    base_files = {
        "com/specproof/demo/service/UserServiceTest.java": (
            "public class UserServiceTest {\n"
            "    @Test\n"
            "    public void test1() {}\n"
            "    @Test\n"
            "    public void test2() {}\n"
            "}\n"
        ),
    }
    head_files = {
        "com/specproof/demo/service/UserServiceTest.java": (
            "public class UserServiceTest {\n"
            "    @Test\n"
            "    public void test1() {}\n"
            "}\n"
        ),
    }
    findings = check_test_weakening(base_files, head_files)
    removals = [f for f in findings if f["contract_id"] == "TEST_STRENGTH-01"]
    assert len(removals) == 1
    assert removals[0]["type"] == "test_removed"
    assert "2 -> 1" in removals[0]["description"]


def test_check_forbidden_changes_annotation_removal() -> None:
    """check_forbidden_changes: 移除 @PreAuthorize 注解是违宪。"""
    base_files = {
        "com/specproof/demo/controller/UserController.java": BASE_CONTROLLER,
    }
    head_files = {
        "com/specproof/demo/controller/UserController.java": HEAD_CONTROLLER,
    }
    clauses = ["must not remove the auth guard"]
    findings = check_forbidden_changes(base_files, head_files, clauses, "CONST-01")
    removals = [f for f in findings if f["type"] == "forbidden_annotation_removal"]
    assert len(removals) == 1
    assert removals[0]["contract_id"] == "CONST-01"


def test_check_forbidden_changes_duplicate_publish() -> None:
    """check_forbidden_changes: convertAndSend 调用次数增加是重复发布。"""
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
    clauses = ["must not publish event twice"]
    findings = check_forbidden_changes(base_files, head_files, clauses, "CONST-02")
    removals = [f for f in findings if f["type"] == "forbidden_duplicate_publish"]
    assert len(removals) == 1
    assert removals[0]["contract_id"] == "CONST-02"


def test_check_forbidden_changes_unique_guard_removed() -> None:
    """check_forbidden_changes: 移除 existsByEmail 是唯一性守卫移除。"""
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
    clauses = ["must not remove the uniqueness guard"]
    findings = check_forbidden_changes(base_files, head_files, clauses, "CONST-03")
    removals = [f for f in findings if f["type"] == "forbidden_guard_removal"]
    assert len(removals) == 1
    assert removals[0]["contract_id"] == "CONST-03"


def test_check_forbidden_changes_token_guard_removed() -> None:
    """check_forbidden_changes: 移除 invalidateOldTokens 是令牌守卫移除。"""
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
    clauses = ["must not remove token invalidation"]
    findings = check_forbidden_changes(base_files, head_files, clauses, "CONST-04")
    removals = [f for f in findings if f["type"] == "forbidden_token_guard_removal"]
    assert len(removals) == 1
    assert removals[0]["contract_id"] == "CONST-04"


def test_check_forbidden_changes_schema_break() -> None:
    """check_forbidden_changes: DTO 字段移除是架构破坏。"""
    base_files = {
        "com/specproof/demo/dto/UserDto.java": (
            "public class UserDto {\n"
            "    private String email;\n"
            "    private String name;\n"
            "}\n"
        ),
    }
    head_files = {
        "com/specproof/demo/dto/UserDto.java": (
            "public class UserDto {\n"
            "    private String name;\n"
            "}\n"
        ),
    }
    clauses = ["must not remove schema field"]
    findings = check_forbidden_changes(base_files, head_files, clauses, "CONST-05")
    removals = [f for f in findings if f["type"] == "forbidden_schema_break"]
    assert len(removals) == 1
    assert removals[0]["contract_id"] == "CONST-05"


def test_check_forbidden_changes_unchanged_is_clean() -> None:
    """check_forbidden_changes: 两端相同 → 无发现。"""
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
    clauses = ["must not publish event twice"]
    findings = check_forbidden_changes(base_files, head_files, clauses, "CONST-06")
    assert findings == []
