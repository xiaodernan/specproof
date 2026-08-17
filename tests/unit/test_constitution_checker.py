"""P2-b unit tests — constitution checker (forbidden changes)."""

from agent.checkers.constitution import check_forbidden_changes

BASE_CTRL = """@RestController
public class UserController {
    @PutMapping("/{id}/email")
    @PreAuthorize("isAuthenticated()")
    public UserResponse changeEmail(Long id) {
        return null;
    }
}
"""

HEAD_NO_AUTH = BASE_CTRL.replace(
    '    @PreAuthorize("isAuthenticated()")\n', ""
)

BASE_SVC = """@Service
public class UserService {
    @Transactional
    public UserResponse changeEmail(Long id) {
        userRepository.save(user);
        invalidateOldTokens(id);
        rabbitTemplate.convertAndSend("specproof.demo.events", event);
        return null;
    }
}
"""

HEAD_DUP_PUBLISH = BASE_SVC.replace(
    'rabbitTemplate.convertAndSend("specproof.demo.events", event);',
    'rabbitTemplate.convertAndSend("specproof.demo.events", event);\n'
    '        rabbitTemplate.convertAndSend("specproof.demo.events", event);',
)


def test_annotation_removal_forbidden_detected():
    findings = check_forbidden_changes(
        {"c/UserController.java": BASE_CTRL},
        {"c/UserController.java": HEAD_NO_AUTH},
        ["must not remove the authentication guard"],
        "AUTH-01",
    )
    assert len(findings) == 1
    assert findings[0]["type"] == "forbidden_annotation_removal"
    assert findings[0]["contract_id"] == "AUTH-01"
    assert findings[0]["evidence_type"] == "constitution_check"


def test_duplicate_publish_forbidden_detected():
    findings = check_forbidden_changes(
        {"s/UserService.java": BASE_SVC},
        {"s/UserService.java": HEAD_DUP_PUBLISH},
        ["must never publish the event twice"],
        "EVENT_ONCE-01",
    )
    assert len(findings) == 1
    assert findings[0]["type"] == "forbidden_duplicate_publish"


def test_no_violation_when_clause_irrelevant():
    findings = check_forbidden_changes(
        {"c/UserController.java": BASE_CTRL},
        {"c/UserController.java": HEAD_NO_AUTH},
        ["must not change the database schema"],
        "AUTH-01",
    )
    # schema clause + no DTO changes -> nothing
    assert findings == []


def test_token_guard_removal_detected():
    head = BASE_SVC.replace("invalidateOldTokens(id);\n        ", "")
    findings = check_forbidden_changes(
        {"s/UserService.java": BASE_SVC},
        {"s/UserService.java": head},
        ["must not remove token invalidation"],
        "TOKEN_INVALIDATION-01",
    )
    assert any(f["type"] == "forbidden_token_guard_removal" for f in findings)
