"""Direct tests for ``_check_http_diff`` — the source-diff half of the
differential node's AUTH-01 evidence.

It scans Base/Head workspaces for non-test Java files and delegates to the
shared AUTH checker (``check_auth_annotations``), so composed custom
annotations (@RequireAuth) and interface-level method security are honored.
A file-level "@PreAuthorize present/absent" diff cannot see either, so this
path is load-bearing for the adversarial cases.

All cases build tmp source trees; nothing runs Maven, Docker, or an adapter.
"""

from __future__ import annotations

from pathlib import Path

from agent.nodes.run_differential import _check_http_diff

CONTROLLER_WITH_AUTH = """package com.specproof.demo.controller;

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

CONTROLLER_WITHOUT_AUTH = """package com.specproof.demo.controller;

@RestController
@RequestMapping("/api/users")
public class UserController {

    @PutMapping("/{id}/email")
    public ResponseEntity<UserResponse> changeEmail(
            @PathVariable Long id,
            @Valid @RequestBody ChangeEmailRequest request) {
        return ResponseEntity.ok(userService.changeEmail(id, request));
    }
}"""

CONTROLLER_WITH_REQUIREAUTH = CONTROLLER_WITH_AUTH.replace(
    '@PreAuthorize("isAuthenticated()")', "@RequireAuth"
)

CONTROLLER_WITH_SECURED = CONTROLLER_WITH_AUTH.replace(
    '@PreAuthorize("isAuthenticated()")', "@Secured(\"ROLE_ADMIN\")"
)

GET_ONLY_CONTROLLER = """package com.specproof.demo.controller;

@RestController
@RequestMapping("/api/users")
public class UserController {

    @GetMapping("/{id}")
    public UserResponse getUser(@PathVariable Long id) {
        return userService.getUser(id);
    }
}"""

CONTROLLER_IMPLEMENTS_INTERFACE = """package com.specproof.demo.controller;

@RestController
@RequestMapping("/api/users")
public class UserController implements UserApi {

    @PutMapping("/{id}/email")
    public ResponseEntity<UserResponse> changeEmail(
            @PathVariable Long id,
            @Valid @RequestBody ChangeEmailRequest request) {
        return ResponseEntity.ok(userService.changeEmail(id, request));
    }
}"""

USER_API_INTERFACE = """package com.specproof.demo.controller;

public interface UserApi {

    @PreAuthorize("isAuthenticated()")
    default ResponseEntity<UserResponse> changeEmail(Long id,
            ChangeEmailRequest request) {
        return null;
    }
}"""


def _write_tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_auth_annotation_removed_is_regression(tmp_path: Path) -> None:
    base = _write_tree(tmp_path / "base", {
        "src/main/java/com/specproof/demo/controller/UserController.java":
            CONTROLLER_WITH_AUTH,
    })
    head = _write_tree(tmp_path / "head", {
        "src/main/java/com/specproof/demo/controller/UserController.java":
            CONTROLLER_WITHOUT_AUTH,
    })

    findings = _check_http_diff(str(base), str(head))

    assert len(findings) == 1
    f = findings[0]
    assert f["verdict"] == "REGRESSION"
    assert f["detail"]
    assert "UserController.java" in f["location"]


def test_composed_custom_annotation_is_no_finding(tmp_path: Path) -> None:
    """@RequireAuth replacing @PreAuthorize is equivalent protection."""
    base = _write_tree(tmp_path / "base", {
        "src/main/java/com/specproof/demo/controller/UserController.java":
            CONTROLLER_WITH_AUTH,
    })
    head = _write_tree(tmp_path / "head", {
        "src/main/java/com/specproof/demo/controller/UserController.java":
            CONTROLLER_WITH_REQUIREAUTH,
    })

    assert _check_http_diff(str(base), str(head)) == []


def test_secured_annotation_removed_is_regression(tmp_path: Path) -> None:
    base = _write_tree(tmp_path / "base", {
        "src/main/java/com/specproof/demo/controller/UserController.java":
            CONTROLLER_WITH_SECURED,
    })
    head = _write_tree(tmp_path / "head", {
        "src/main/java/com/specproof/demo/controller/UserController.java":
            CONTROLLER_WITHOUT_AUTH,
    })

    findings = _check_http_diff(str(base), str(head))
    assert len(findings) == 1
    assert findings[0]["verdict"] == "REGRESSION"


def test_interface_level_protection_is_no_finding(tmp_path: Path) -> None:
    """An @PreAuthorize on an implemented interface's default method keeps
    the endpoint protected even when the controller drops its own annotation."""
    base = _write_tree(tmp_path / "base", {
        "src/main/java/com/specproof/demo/controller/UserController.java":
            CONTROLLER_WITH_AUTH,
        "src/main/java/com/specproof/demo/controller/UserApi.java":
            USER_API_INTERFACE,
    })
    head = _write_tree(tmp_path / "head", {
        "src/main/java/com/specproof/demo/controller/UserController.java":
            CONTROLLER_IMPLEMENTS_INTERFACE,
        "src/main/java/com/specproof/demo/controller/UserApi.java":
            USER_API_INTERFACE,
    })

    assert _check_http_diff(str(base), str(head)) == []


def test_get_only_controller_is_no_finding(tmp_path: Path) -> None:
    """Non-mutating endpoints are not in scope."""
    base = _write_tree(tmp_path / "base", {
        "src/main/java/com/specproof/demo/controller/UserController.java":
            GET_ONLY_CONTROLLER,
    })
    head = _write_tree(tmp_path / "head", {
        "src/main/java/com/specproof/demo/controller/UserController.java":
            GET_ONLY_CONTROLLER,
    })

    assert _check_http_diff(str(base), str(head)) == []


def test_identical_trees_are_no_finding(tmp_path: Path) -> None:
    base = _write_tree(tmp_path / "base", {
        "src/main/java/com/specproof/demo/controller/UserController.java":
            CONTROLLER_WITH_AUTH,
    })
    head = _write_tree(tmp_path / "head", {
        "src/main/java/com/specproof/demo/controller/UserController.java":
            CONTROLLER_WITH_AUTH,
    })

    assert _check_http_diff(str(base), str(head)) == []
