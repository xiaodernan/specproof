"""One shared decision: what makes a findings report "clean".

Two scanners in this package produce reports of the same shape — the
LOCAL payload-directory scan (``evidence/orphan_scan.py``) and the
bucket/index reconciliation (``evidence/bucket_reconcile.py``). "A report
with no findings is clean" is **one** decision, so it is written once
here instead of being copied into both report classes.

The clone ratchet (``tests/unit/test_structural_clone_ratchet.py``) is
what pointed at the copy: it flagged two same-name ``is_clean`` methods
whose bodies were identical. Sharing the implementation is the answer it
asks for first ("share the implementation, or add the group to
KNOWN_NEAR_CLONES with the reason it must stay duplicated") — and here
there is no reason it must stay duplicated, so it does not.

Both report kinds still answer the question in their own vocabulary:
``orphan_scan`` reports dangling / orphan / digest-mismatch findings over
a directory, ``bucket_reconcile`` reports unindexed / missing /
digest-mismatch / ambiguous-index findings over the buckets. What they
share is only the emptiness rule, and that is the part that must not
drift: two scanners that disagree about what "clean" means would hand an
operator two contradicting verdicts about the same evidence chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FindingsReport[FindingT]:
    """Base for a report that is a list of findings plus what was scanned."""

    findings: list[FindingT] = field(default_factory=list)

    def is_clean(self) -> bool:
        """No findings — nothing is broken, as far as this scan can tell."""
        return not self.findings


__all__ = ["FindingsReport"]
