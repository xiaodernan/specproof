"""Unit tests for agent.fixes — deterministic fix proposals (P5)."""

from pathlib import Path

from agent.fixes import (
    FixProposal,
    apply_fix,
    propose_fixes,
    render_fix_summary,
)

CONTROLLER_BASE = """package com.example;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;

public class UserController {

    @PostMapping("/change-email")
    @PreAuthorize("isAuthenticated()")
    public void changeEmail() {
        System.out.println("base");
    }
}
"""

CONTROLLER_HEAD = """package com.example;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;

public class UserController {

    @PostMapping("/change-email")
    public void changeEmail() {
        System.out.println("head");
    }
}
"""

SERVICE_BASE = """package com.example;

public class UserService {

    public void changeEmail(String email) {
        user.setEmail(email);
        tokenService.invalidateOldTokens(user);
        rabbitTemplate.convertAndSend("email.changed", event);
    }
}
"""

SERVICE_HEAD_NO_TOKEN = """package com.example;

public class UserService {

    public void changeEmail(String email) {
        user.setEmail(email);
        rabbitTemplate.convertAndSend("email.changed", event);
    }
}
"""

SERVICE_HEAD_WRONG_KEY = """package com.example;

public class UserService {

    public void changeEmail(String email) {
        user.setEmail(email);
        tokenService.invalidateOldTokens(user);
        rabbitTemplate.convertAndSend("email.changed.typo", event);
    }
}
"""

SERVICE_HEAD_DUP_PUBLISH = """package com.example;

public class UserService {

    public void changeEmail(String email) {
        user.setEmail(email);
        tokenService.invalidateOldTokens(user);
        rabbitTemplate.convertAndSend("email.changed", event);
        rabbitTemplate.convertAndSend("email.changed", event);
    }
}
"""

DTO_BASE = """package com.example;

import jakarta.validation.constraints.NotBlank;

public class ChangeEmailRequest {

    @NotBlank
    private String email;
}
"""

DTO_HEAD = """package com.example;

import jakarta.validation.constraints.NotBlank;

public class ChangeEmailRequest {

    private String email;
}
"""


def _write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _finding(contract_id: str, location: str, description: str,
             finding_id: str = "F-1") -> dict:
    return {
        "id": finding_id,
        "contract_id": contract_id,
        "severity": "MAJOR",
        "type": "",
        "location": location,
        "evidence_type": "java_source_diff",
        "confidence": 0.85,
        "description": description,
    }


def test_annotation_restore_proposal(tmp_path: Path):
    base, head = tmp_path / "base", tmp_path / "head"
    _write_tree(base, {"src/UserController.java": CONTROLLER_BASE})
    _write_tree(head, {"src/UserController.java": CONTROLLER_HEAD})
    finding = _finding(
        "AUTH-01",
        "src/UserController.java",
        "Security annotation removed from mutating endpoint method "
        "changeEmail() in src/UserController.java",
    )
    proposals, skipped = propose_fixes([finding], base, head)
    assert skipped == []
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.fix_id == "FIX-AUTH-01-01"
    assert proposal.action == "insert_lines"
    assert proposal.base_lines == ['    @PreAuthorize("isAuthenticated()")']
    assert proposal.anchor_line >= 1
    assert proposal.head_context.strip() == "public void changeEmail() {"
    assert "@@" in proposal.patch or "+" in proposal.patch


def test_annotation_present_in_head_skips(tmp_path: Path):
    base, head = tmp_path / "base", tmp_path / "head"
    _write_tree(base, {"src/UserController.java": CONTROLLER_BASE})
    _write_tree(head, {"src/UserController.java": CONTROLLER_BASE})
    finding = _finding(
        "AUTH-01", "src/UserController.java", "method changeEmail()"
    )
    proposals, skipped = propose_fixes([finding], base, head)
    assert proposals == []
    assert skipped and "deterministic" in skipped[0]["reason"]


def test_token_call_restore_proposal(tmp_path: Path):
    base, head = tmp_path / "base", tmp_path / "head"
    _write_tree(base, {"src/UserService.java": SERVICE_BASE})
    _write_tree(head, {"src/UserService.java": SERVICE_HEAD_NO_TOKEN})
    finding = _finding(
        "TOKEN_INVALIDATION-01",
        "src/UserService.java",
        "Token invalidation call removed from method changeEmail() in "
        "src/UserService.java",
    )
    proposals, skipped = propose_fixes([finding], base, head)
    assert skipped == []
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.fix_id == "FIX-TOKEN_INVALIDATION-01-01"
    assert proposal.action == "insert_lines"
    assert any(
        "invalidateOldTokens" in line for line in proposal.base_lines
    )
    assert proposal.head_context.strip() == "}"


def test_routing_key_replace_proposal(tmp_path: Path):
    base, head = tmp_path / "base", tmp_path / "head"
    _write_tree(base, {"src/UserService.java": SERVICE_BASE})
    _write_tree(head, {"src/UserService.java": SERVICE_HEAD_WRONG_KEY})
    finding = _finding(
        "EVENT_ONCE-01",
        "src/UserService.java",
        "Event publish call changed in src/UserService.java",
    )
    proposals, skipped = propose_fixes([finding], base, head)
    assert skipped == []
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.action == "replace_lines"
    assert proposal.base_lines[0].strip().endswith(
        'convertAndSend("email.changed", event);'
    )
    assert proposal.head_lines[0].strip().endswith(
        'convertAndSend("email.changed.typo", event);'
    )


def test_duplicate_publish_remove_proposal(tmp_path: Path):
    base, head = tmp_path / "base", tmp_path / "head"
    _write_tree(base, {"src/UserService.java": SERVICE_BASE})
    _write_tree(head, {"src/UserService.java": SERVICE_HEAD_DUP_PUBLISH})
    finding = _finding(
        "EVENT_ONCE-01",
        "src/UserService.java",
        "Event publish count increased in src/UserService.java: 1 -> 2",
    )
    proposals, skipped = propose_fixes([finding], base, head)
    assert skipped == []
    assert len(proposals) == 1
    assert proposals[0].action == "remove_lines"
    assert proposals[0].head_lines[0].strip().endswith("convertAndSend("
        '"email.changed", event);')


def test_validation_restore_proposal(tmp_path: Path):
    base, head = tmp_path / "base", tmp_path / "head"
    _write_tree(base, {"src/ChangeEmailRequest.java": DTO_BASE})
    _write_tree(head, {"src/ChangeEmailRequest.java": DTO_HEAD})
    finding = _finding(
        "UNIQUE-01",
        "src/ChangeEmailRequest.java",
        "Blank email accepted — validation removed",
    )
    proposals, skipped = propose_fixes([finding], base, head)
    assert skipped == []
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.action == "insert_lines"
    assert proposal.base_lines == ["    @NotBlank"]
    assert proposal.head_context.strip() == "private String email;"


def test_unknown_contract_skipped(tmp_path: Path):
    base, head = tmp_path / "base", tmp_path / "head"
    _write_tree(base, {"src/A.java": "class A {}\n"})
    _write_tree(head, {"src/A.java": "class A {}\n"})
    finding = _finding("PERF-01", "src/A.java", "N+1 queries")
    proposals, skipped = propose_fixes([finding], base, head)
    assert proposals == []
    assert len(skipped) == 1


def test_apply_fix_inserts_and_guards_drift(tmp_path: Path):
    base, head = tmp_path / "base", tmp_path / "head"
    _write_tree(base, {"src/UserController.java": CONTROLLER_BASE})
    _write_tree(head, {"src/UserController.java": CONTROLLER_HEAD})
    finding = _finding(
        "AUTH-01", "src/UserController.java", "method changeEmail()"
    )
    proposals, _skipped = propose_fixes([finding], base, head)
    proposal = proposals[0]
    assert apply_fix(proposal, head)
    fixed = (head / "src/UserController.java").read_text(encoding="utf-8")
    assert '@PreAuthorize("isAuthenticated()")' in fixed
    # Second application: anchor line changed -> drift guard rejects.
    assert not apply_fix(proposal, head)


def test_apply_fix_on_stale_anchor_rejects(tmp_path: Path):
    base, head = tmp_path / "base", tmp_path / "head"
    _write_tree(base, {"src/UserController.java": CONTROLLER_BASE})
    _write_tree(head, {"src/UserController.java": CONTROLLER_HEAD})
    finding = _finding(
        "AUTH-01", "src/UserController.java", "method changeEmail()"
    )
    proposals, _skipped = propose_fixes([finding], base, head)
    proposal = proposals[0]
    stale = FixProposal(**{**proposal.to_dict(),
                           "head_context": "totally different line"})
    assert not apply_fix(stale, head)


def test_render_fix_summary_lists_proposals_and_skips(tmp_path: Path):
    base, head = tmp_path / "base", tmp_path / "head"
    _write_tree(base, {"src/UserController.java": CONTROLLER_BASE})
    _write_tree(head, {"src/UserController.java": CONTROLLER_HEAD})
    finding = _finding(
        "AUTH-01", "src/UserController.java", "method changeEmail()"
    )
    proposals, skipped = propose_fixes(
        [finding, _finding("PERF-01", "src/UserController.java", "N+1")],
        base, head,
    )
    text = render_fix_summary(proposals, skipped)
    assert "FIX-AUTH-01-01" in text
    assert "Skipped" in text
