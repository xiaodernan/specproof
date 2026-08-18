"""P2 unit tests — endpoint surface checker (OPENAPI-01)."""

from agent.checkers.java_source import check_endpoint_changes

BASE_CONTROLLER = """@RestController
@RequestMapping("/api/users")
public class UserController {

    @GetMapping("/{id}")
    public UserResponse getUser(Long id) {
        return null;
    }

    @PutMapping("/{id}/email")
    public UserResponse changeEmail(Long id, ChangeEmailRequest request) {
        return null;
    }
}
"""

HEAD_REMOVED_ENDPOINT = BASE_CONTROLLER.replace(
    '    @GetMapping("/{id}")\n    public UserResponse getUser(Long id) {',
    '    // endpoint removed\n    public UserResponse getUser(Long id) {',
)


def test_endpoint_removal_detected():
    rel = "com/specproof/demo/controller/UserController.java"
    findings = check_endpoint_changes(
        {rel: BASE_CONTROLLER}, {rel: HEAD_REMOVED_ENDPOINT},
    )
    assert len(findings) == 1
    assert findings[0]["contract_id"] == "OPENAPI-01"
    assert findings[0]["type"] == "endpoint_removed"
    assert "GET /{id}" in findings[0]["description"]


def test_identical_surface_no_findings():
    rel = "com/specproof/demo/controller/UserController.java"
    findings = check_endpoint_changes(
        {rel: BASE_CONTROLLER}, {rel: BASE_CONTROLLER},
    )
    assert findings == []


def test_non_controller_files_ignored():
    rel = "com/specproof/demo/service/UserService.java"
    findings = check_endpoint_changes(
        {rel: "class UserService {}"}, {rel: "class UserService {}"},
    )
    assert findings == []


def test_method_rename_refactor_not_flagged():
    """Renaming the Java method (same verb+path) is NOT a surface break."""
    head = BASE_CONTROLLER.replace("getUser", "fetchUser")
    rel = "com/specproof/demo/controller/UserController.java"
    findings = check_endpoint_changes({rel: BASE_CONTROLLER}, {rel: head})
    assert findings == []
