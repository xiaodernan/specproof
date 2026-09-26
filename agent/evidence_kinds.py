"""The evidence kinds a finding can carry, declared once (#87).

``findings.evidence_type`` is a ``VARCHAR(64)`` — unlike ``severity`` there is no
ENUM to act as an authoritative value set. Before this module the only
"vocabulary" was whatever the emitters happened to write, plus a stale copy in
``apps/web/src/ui/toneMap.ts`` that still named ``runtime_test``/``review``
(nothing emits them) and omitted six kinds the pipeline does emit — so those six
reached a reviewer as raw English.

This frozenset is the declaration; ``tests/unit/test_evidence_vocabulary_parity.py``
keeps both ends honest: every token a producer writes must be declared, every
declared token must have a producer, and the Web glossary must equal this set.

Producers are still free to write string literals (rewriting 12 call sites would
be a bigger risk than the drift it prevents) — the gate is what makes the
declaration authoritative rather than aspirational.
"""
from __future__ import annotations

from typing import Final

EVIDENCE_KINDS: Final[frozenset[str]] = frozenset(
    {
        # Static source verdicts — no code was executed.
        "java_source_diff",
        "constitution_check",
        "static_analysis",
        # Executed differentials: base vs head, or a probe against existing
        # behaviour. The surface they ran on is a separate disclosure (#50/#54).
        "self_test_diff",
        "base_pass_head_fail",
        "differential_execution",
        "probe_differential",
        # A crashing checker is a finding, not silence.
        "checker_failed",
        # Written when a finding carries no evidence_type at all
        # (`create_capsule.py:185`, `inline_comments.py:132`) — so a PR comment
        # and a capsule can both say "unknown". Renaming it would be a nicer
        # lie; declaring it is what makes the surfaces agree.
        "unknown",
    }
)
