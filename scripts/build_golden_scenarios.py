"""Build the honest golden-scenario tags for the SpecProof demo repo.

Reproducible scenario construction (v2):
- Repoints tag "base" to the honest base state: SecurityConfig permitAll
  (HTTP layer open) + @PreAuthorize on the mutating endpoint, so method
  security is the ONLY auth control — the regression is real.
- Repoints tag "head-v1" to the honest head state: same, minus the
  @PreAuthorize annotation (the injected regression).
- Creates one tag per golden case: case-XX-head = base + one injected bug.
- Each mutation is a committed, reviewable change to demo/ files only.

Run from the repository root:
    python scripts/build_golden_scenarios.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO = "demo/spring-backend/src/main/java/com/specproof/demo"
CONTROLLER = DEMO + "/controller/UserController.java"
SERVICE = DEMO + "/service/UserService.java"
DTO = DEMO + "/dto/UserResponse.java"
SECURITY = DEMO + "/config/SecurityConfig.java"

AUTH_IMPORT = "import org.springframework.security.access.prepost.PreAuthorize;\n"
AUTH_ANNOTATION = '    @PreAuthorize("isAuthenticated()")\n'
TX_ANNOTATION = "    @Transactional\n"
SAVE_CALL = "        userRepository.save(user);"
INVALIDATE_CALL = "        invalidateOldTokens(userId);\n\n"
DUPLICATE_GUARD = """        if (userRepository.existsByEmail(newEmail)) {
            throw new RuntimeException("Email already in use: " + newEmail);
        }

"""
EVENT_BLOCK = """        rabbitTemplate.convertAndSend(
                "specproof.demo.events",
                "email.changed",
                event);
"""


def git(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "git " + " ".join(args) + " failed: " + proc.stderr.strip()[:400]
        )
    return proc.stdout.strip()


def require_clean() -> None:
    out = git("status", "--porcelain")
    if out.strip():
        raise RuntimeError("Working tree is not clean. Commit or stash first.\n" + out)


def read_demo(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def write_demo(rel: str, content: str) -> None:
    (REPO_ROOT / rel).write_text(content, encoding="utf-8")


def replace_exact(rel: str, old: str, new: str) -> None:
    content = read_demo(rel)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(
            "Expected exactly 1 occurrence in " + rel + ", found " + str(count)
            + " for: " + old[:60]
        )
    write_demo(rel, content.replace(old, new))


def remove_line_containing(rel: str, needle: str) -> None:
    """Remove the single full line containing needle (imports etc.)."""
    content = read_demo(rel)
    lines = content.splitlines(keepends=True)
    matches = [i for i, ln in enumerate(lines) if needle in ln]
    if len(matches) != 1:
        raise RuntimeError(
            "Expected exactly 1 line containing " + needle + " in " + rel
            + ", found " + str(len(matches))
        )
    del lines[matches[0]]
    write_demo(rel, "".join(lines))


def commit_and_tag(commit_msg: str, tag: str) -> None:
    git("add", "demo/")
    git("commit", "-m", commit_msg)
    git("tag", "-f", tag, "HEAD")


def restore_base() -> None:
    # Restore only main sources from the (honest) base tag — never touch
    # mvnw/.mvn, tests, or the file-based H2 test profile. --staged keeps the
    # index consistent so the post-condition check sees a clean tree.
    git("restore", "--source=base", "--staged", "--worktree", "--",
        "demo/spring-backend/src/main/java/")


def apply_case(case: str, commit_msg: str, mutations: list[tuple[str, str, str]]) -> None:
    """mutations: list of (rel_file, old, new)."""
    for rel, old, new in mutations:
        replace_exact(rel, old, new)
    commit_and_tag("Golden case " + case + ": " + commit_msg, case + "-head")
    restore_base()


def main() -> None:
    require_clean()

    # 1. Honest head = current demo state (permitAll, no @PreAuthorize).
    head_commit = git("rev-parse", "HEAD")
    git("tag", "-f", "head-v1", head_commit)
    print("head-v1 ->", head_commit)

    # 2. Honest base = old base demo files (authenticated + @PreAuthorize)
    #    with the HTTP filter chain opened, so method security is the only
    #    auth control and the @PreAuthorize removal is a real regression.
    git("restore", "--source=base", "--", "demo/spring-backend/src/main/java/")
    replace_exact(
        SECURITY,
        "                .anyRequest().authenticated()",
        "                .anyRequest().permitAll()",
    )
    commit_and_tag(
        "Golden scenarios: honest base — permitAll filter chain, "
        "@PreAuthorize is the only auth control",
        "base",
    )
    print("base ->", git("rev-parse", "HEAD"))

    # 3. Per-case bug injections (each on top of honest base).
    apply_case(
        "case-02",
        "remove @Transactional from changeEmail (transactional removal)",
        [(SERVICE, TX_ANNOTATION, "")],
    )
    apply_case(
        "case-03",
        "clean PR: add a new read-only endpoint",
        [(CONTROLLER, '    @GetMapping("/{id}")', CLEAN_ENDPOINT_ADD + '    @GetMapping("/{id}")')],
    )
    apply_case(
        "case-04",
        "remove the duplicate-email guard",
        [(SERVICE, DUPLICATE_GUARD, "")],
    )
    apply_case(
        "case-05",
        "remove token invalidation after email change",
        [(SERVICE, INVALIDATE_CALL, "")],
    )
    apply_case(
        "case-06",
        "rename UserResponse.email to emailAddress (schema break)",
        [
            (DTO, "    private String email;", "    private String emailAddress;"),
            (DTO, "        this.email = email;", "        this.emailAddress = email;"),
            (DTO, "    public String getEmail() { return email; }",
             "    public String getEmailAddress() { return emailAddress; }"),
            (DTO, "    public void setEmail(String email) { this.email = email; }",
             "    public void setEmailAddress(String emailAddress) { "
             "this.emailAddress = emailAddress; }"),
        ],
    )
    apply_case(
        "case-07",
        "publish the email.changed event twice",
        [(SERVICE, EVENT_BLOCK, EVENT_BLOCK + EVENT_BLOCK)],
    )
    apply_case(
        "case-08",
        "transaction split: drop @Transactional and add a second write op",
        [
            (SERVICE, TX_ANNOTATION, ""),
            (SERVICE, SAVE_CALL, SAVE_CALL + "\n        userRepository.saveAndFlush(user);"),
        ],
    )
    _remove_controller_annotation()
    apply_case(
        "case-09",
        "multi-security: remove @PreAuthorize AND @Transactional",
        [
            (SERVICE, TX_ANNOTATION, ""),
        ],
    )
    apply_case(
        "case-10",
        "comment-only change",
        [(CONTROLLER, "@RestController", COMMENT_ADD + "@RestController")],
    )

    # 4. Leave the working tree at honest base (all demo tests green).
    restore_base()
    if git("status", "--porcelain"):
        raise RuntimeError("Post-condition failed: working tree not clean")
    print("All golden scenario tags built:")
    print(git("tag", "-l"))


def _remove_controller_annotation() -> None:
    """Remove the @PreAuthorize import + annotation from the controller."""
    remove_line_containing(
        CONTROLLER, "import org.springframework.security.access.prepost.PreAuthorize;"
    )
    replace_exact(CONTROLLER, AUTH_ANNOTATION, "")


CLEAN_ENDPOINT_ADD = """    @GetMapping("/{id}/email")
    public ResponseEntity<String> getUserEmail(@PathVariable Long id) {
        return ResponseEntity.ok(userService.getUser(id).getEmail());
    }

"""

COMMENT_ADD = """/**
 * Demo controller for SpecProof golden scenarios.
 * This comment documents nothing behavioural and must not trigger findings.
 */
"""


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(1)
