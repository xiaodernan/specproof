"""#253 — case-17's regression is a one-line logic inversion whose persisted
effect is wiped by the test harness, so its DB-state evidence is unreliable.

#249 established that case-17's severity was capped at MAJOR because the
differential read DB_CONSISTENT (identical base/head H2 dumps). #252 noted the
generated UNIQUE test is non-transactional, so the "assertion failure rolled the
transaction back" explanation was wrong, and concluded the DB consistency is
otherwise unexplained. This test pins the actual code-level cause, read directly
from the golden-case fixture:

1. case-17-head inverts ONE line in UserService.changeEmail:
       base : if (userRepository.existsByEmail(newEmail)) throw   // reject duplicate
       head : if (!userRepository.existsByEmail(newEmail)) throw  // accept duplicate
   So the regressed head ACCEPTS the duplicate and — because changeEmail is
   @Transactional — COMMITS it (bob's email becomes alice@example.com).
2. The generated SpecProofGeneratedTest class is non-transactional and its
   @BeforeEach calls userRepository.deleteAll(). A later test method's setUp
   therefore wipes bob's persisted mutation before the differential's DB dump is
   taken. DB_CONSISTENT is thus a harness artifact, NOT evidence that no
   mutation occurred.

Consequence: case-17's BLOCKER-vs-MAJOR severity is underdetermined by the
current DB evidence. The honest fix is in-flight DB capture during the head
regression response (#249 candidate ② / original #253 intent) — this test does
NOT implement that; it only pins the diagnosis so a future refactor of the
golden case cannot silently change what case-17 means.
"""

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
USER_SERVICE = (
    "demo/spring-backend/src/main/java/com/specproof/demo/service/"
    "UserService.java"
)
#: The generated source moved into the TEMPLATE layer (#319: the node
#: became pipeline, the template became the library), so the pin reads
#: the template that writes the class AND the rendered golden artifact —
#: the byte-for-byte copy of what actually gets compiled and run.
TEMPLATE_SRC = REPO / "agent" / "experiments" / "templates.py"
GOLDEN_SRC = REPO / "tests" / "unit" / "golden" / "generated_test_demo.java"


def _git_show(repo: Path, ref: str, path: str) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(repo), "show", f"{ref}:{path}"],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=30,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    return proc.stdout


def test_case17_head_inverts_the_duplicate_email_guard():
    base = _git_show(REPO, "base", USER_SERVICE)
    head = _git_show(REPO, "case-17-head", USER_SERVICE)
    if base is None or head is None:
        pytest.skip("case-17 golden-case refs unavailable in this checkout")

    # base rejects duplicates (correct behaviour)
    assert "if (userRepository.existsByEmail(newEmail))" in base
    assert "if (!userRepository.existsByEmail(newEmail))" not in base
    # case-17-head accepts duplicates (the regression)
    assert "if (!userRepository.existsByEmail(newEmail))" in head
    assert "if (userRepository.existsByEmail(newEmail))" not in head


def test_changeemail_is_transactional_so_acceptance_commits():
    head = _git_show(REPO, "case-17-head", USER_SERVICE)
    if head is None:
        pytest.skip("case-17-head ref unavailable in this checkout")
    # @Transactional on the method means a successful (non-throwing) change
    # commits the mutation; only a thrown exception rolls it back. So when the
    # regressed guard accepts the duplicate, the change is persisted.
    assert "@Transactional" in head
    assert "public UserResponse changeEmail" in head


def test_generated_test_class_is_non_transactional_but_resets_db():
    if not GOLDEN_SRC.exists():
        pytest.skip("generated source not present")
    src = GOLDEN_SRC.read_text(encoding="utf-8")
    # The generated test class header carries NO @Transactional — so a failed
    # assertion does NOT roll anything back (this is exactly why #252 rejected
    # the "rollback" explanation).
    header_start = src.index("@SpringBootTest")
    header_end = src.index("public class SpecProofGeneratedTest")
    header = src[header_start:header_end]
    assert "@Transactional" not in header
    # Yet every test method starts from a wiped DB, which is what erases the
    # persisted duplicate before the differential's dump is taken.
    assert "@BeforeEach" in src
    assert "userRepository.deleteAll()" in src


def test_the_template_that_writes_the_class_keeps_that_shape():
    """The golden artifact pins what is COMPILED; the template pins where
    it comes from. Both must say the same thing — or the diagnosis this
    file pins (non-transactional class, wiped DB before every method)
    drifts silently away from the code that is actually generated."""
    if not TEMPLATE_SRC.exists():
        pytest.skip("template source not present")
    src = TEMPLATE_SRC.read_text(encoding="utf-8")
    header_start = src.index("@SpringBootTest")
    header_end = src.index("public class SpecProofGeneratedTest")
    header = src[header_start:header_end]
    assert "@Transactional" not in header
    assert "@BeforeEach" in src
    assert "@@user_repo@@.deleteAll()" in src
