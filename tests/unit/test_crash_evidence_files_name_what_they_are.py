"""The crash-semantics files must keep saying what they actually are.

Two files in this repository assert the *shape* of the P1.6 crash semantics
against local dicts and lists. That is a legitimate thing to write down — but
it is a MODEL, and a reader who opens a green file has no way to tell a model
from evidence unless the file says so.

This gate is that "unless the file says so":

  * every class in the two model files must declare its nature — either
    ``MODEL`` (it asserts an intention) or ``PRODUCTION CODE`` (it calls the
    real thing);
  * both files must point at the file that carries the real evidence
    (``tests/integration/test_worker_checkpoint_survives_a_crash.py`` — real
    saver, real MongoDB, a fresh saver standing in for the restarted worker);
  * that evidence file must exist and must actually have legs;
  * the old over-claim — "these tests verify the checkpoint-and-recovery
    logic" — must not come back: a model file that says it verifies the
    machinery is the exact defect this gate exists to prevent.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MODEL_FILES = (
    ROOT / "tests" / "unit" / "test_checkpoint_recovery.py",
    ROOT / "tests" / "integration" / "test_worker_crash_mid_graph.py",
)

#: The file that carries the real evidence (real saver, real MongoDB).
EVIDENCE_FILE = ROOT / "tests" / "integration" / "test_worker_checkpoint_survives_a_crash.py"

#: The claim that must not come back.
OVERCLAIM = "verify the checkpoint-and-recovery logic"


def _classes(path: Path) -> list[ast.ClassDef]:
    """Only the classes that carry legs — helper classes are not claims."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    out: list[ast.ClassDef] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if any(
            isinstance(child, ast.FunctionDef) and child.name.startswith("test_")
            for child in node.body
        ):
            out.append(node)
    return out


def test_the_evidence_file_exists_and_has_legs() -> None:
    assert EVIDENCE_FILE.is_file(), (
        f"{EVIDENCE_FILE} is gone — the two model files point at it as the "
        "proof that a checkpoint survives a crash; without it they point at "
        "nothing"
    )
    tree = ast.parse(EVIDENCE_FILE.read_text(encoding="utf-8-sig"))
    legs = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]
    assert len(legs) >= 3, (
        f"{EVIDENCE_FILE} has {len(legs)} legs — the model files' pointer to "
        "it is a promise that the real proof is there"
    )


def test_every_model_file_points_at_the_real_evidence() -> None:
    for path in MODEL_FILES:
        text = path.read_text(encoding="utf-8-sig")
        assert "test_worker_checkpoint_survives_a_crash.py" in text, (
            f"{path} does not name the file that carries the real evidence — "
            "a reader of a green model file must be able to find the proof in "
            "one hop"
        )


def test_no_model_file_claims_to_verify_the_machinery() -> None:
    for path in MODEL_FILES:
        text = path.read_text(encoding="utf-8-sig")
        assert OVERCLAIM not in text, (
            f"{path} says it verifies the checkpoint-and-recovery logic. The "
            "legs in it assert models; the machinery is exercised in "
            f"{EVIDENCE_FILE.name}. Say what the file is."
        )


def test_every_class_in_a_model_file_declares_its_nature() -> None:
    for path in MODEL_FILES:
        for node in _classes(path):
            doc = ast.get_docstring(node) or ""
            assert ("MODEL" in doc) or ("PRODUCTION CODE" in doc), (
                f"{path.name}::{node.name} has a docstring that does not say "
                "whether its legs are models or production code: "
                f"{doc.splitlines()[0] if doc else '(no docstring)'!r}"
            )
