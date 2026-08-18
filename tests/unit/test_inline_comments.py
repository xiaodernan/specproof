"""Unit tests for integrations.inline_comments (P5 Inline Findings)."""

from integrations.inline_comments import (
    INLINE_MAX,
    _comment_body,
    build_review_comments,
    locate_finding,
    parse_hunks,
)

ANNOTATION_DIFF = "\n".join([
    "diff --git a/src/UserController.java b/src/UserController.java",
    "index 111..222 100644",
    "--- a/src/UserController.java",
    "+++ b/src/UserController.java",
    "@@ -10,6 +10,5 @@ public class UserController {",
    "     private final UserService service;",
    " ",
    "     @PostMapping(\"/change-email\")",
    "-    @PreAuthorize(\"isAuthenticated()\")",
    "     public void changeEmail() {",
    "         service.changeEmail();",
    "     }",
    "",
])

ROUTING_KEY_DIFF = """diff --git a/src/UserService.java b/src/UserService.java
index 333..444 100644
--- a/src/UserService.java
+++ b/src/UserService.java
@@ -30,7 +30,7 @@ public class UserService {
         user.setEmail(newEmail);
         userRepository.saveAndFlush(user);
-        rabbitTemplate.convertAndSend("email.changed", event);
+        rabbitTemplate.convertAndSend("email.changed.typo", event);
     }
 }
"""

PURE_DELETION_DIFF = """diff --git a/src/UserService.java b/src/UserService.java
index 555..666 100644
--- a/src/UserService.java
+++ b/src/UserService.java
@@ -40,4 +40,3 @@ public class UserService {
     public void extra() {
-        tokenService.invalidateOldTokens(user);
     }
 }
"""

ANNOTATION_FINDING = {
    "id": "SRC-AUTH-ANNO",
    "contract_id": "AUTH-01",
    "severity": "MAJOR",
    "type": "annotation_removed",
    "location": "src/UserController.java",
    "evidence_type": "java_source_diff",
    "confidence": 0.85,
    "description": "Security annotation removed from method changeEmail()",
}

EVENT_FINDING = {
    "id": "SRC-EVENT-DUP",
    "contract_id": "EVENT_ONCE-01",
    "severity": "BLOCKER",
    "type": "duplicate_publish",
    "location": "src/UserService.java",
    "evidence_type": "differential_execution",
    "confidence": 0.9,
    "description": "Event published to the wrong routing key",
}


def test_parse_hunks_finds_new_start_and_anchor():
    hunks = parse_hunks(ANNOTATION_DIFF)
    assert len(hunks) == 1
    assert hunks[0].new_start == 10
    # First context line is the class-body line at new-file line 10.
    assert hunks[0].anchor() == 10


def test_locate_annotation_removal_anchors_on_context_line():
    located = locate_finding(
        ANNOTATION_FINDING, {"src/UserController.java": ANNOTATION_DIFF}
    )
    assert located == ("src/UserController.java", 10)


def test_locate_unknown_path_returns_none():
    assert locate_finding(ANNOTATION_FINDING, {}) is None
    assert (
        locate_finding(
            ANNOTATION_FINDING, {"other/File.java": ANNOTATION_DIFF}
        )
        is None
    )


def test_locate_pure_deletion_uses_available_context():
    finding = dict(ANNOTATION_FINDING, location="src/UserService.java")
    located = locate_finding(
        finding, {"src/UserService.java": PURE_DELETION_DIFF}
    )
    # The hunk has a context line ("    }"), so it is anchorable.
    assert located is not None
    path, line = located
    assert path == "src/UserService.java"
    assert line >= 1


def test_locate_without_any_context_line_returns_none():
    diff = """diff --git a/A.java b/A.java
index 1..2 100644
--- a/A.java
+++ b/A.java
@@ -1,1 +0,0 @@
-package demo;
"""
    assert locate_finding(ANNOTATION_FINDING, {"A.java": diff}) is None


def test_build_review_comments_orders_caps_and_dedupes():
    findings = [
        ANNOTATION_FINDING,
        EVENT_FINDING,
        dict(ANNOTATION_FINDING, id="dup-same-location"),
    ]
    diff_by_file = {
        "src/UserController.java": ANNOTATION_DIFF,
        "src/UserService.java": ROUTING_KEY_DIFF,
    }
    comments = build_review_comments(findings, diff_by_file)
    assert len(comments) == 2  # third dedupes onto the first location
    assert comments[0]["path"] == "src/UserService.java"  # BLOCKER first
    assert comments[0]["side"] == "RIGHT"
    assert comments[0]["line"] >= 1
    assert "EVENT_ONCE-01" in comments[0]["body"]
    assert comments[1]["path"] == "src/UserController.java"


def test_build_review_comments_respects_max():
    # Distinct locations: same-location findings merge by design (dedupe),
    # so the cap is only observable across distinct anchor locations.
    findings = []
    diff_by_file = {}
    for index in range(INLINE_MAX + 5):
        path = f"src/Controller{index}.java"
        findings.append(
            dict(ANNOTATION_FINDING, id=f"f-{index}", location=path)
        )
        diff_by_file[path] = ANNOTATION_DIFF
    comments = build_review_comments(findings, diff_by_file, max_comments=3)
    assert len(comments) == 3


def test_comment_body_mentions_evidence_and_replay():
    body = _comment_body(ANNOTATION_FINDING)
    assert "AUTH-01" in body
    assert "MAJOR" in body
    assert "java_source_diff" in body
    assert "specproof replay" in body
