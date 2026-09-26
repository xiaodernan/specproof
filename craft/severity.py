"""The severities an acceptance finding can carry, declared once (#86).

The independent-acceptance lane (`craft`) writes findings into `accept.json` with
a severity scale that is NOT the verification platform's
`findings.severity` ENUM: the secret scanner reports CRITICAL/HIGH/MEDIUM/LOW
(`agent/security_scanner.py::_SECRET_PATTERNS`), while craft's own helpers fall
back to BLOCKER/MAJOR. Only CRITICAL and HIGH are counted as blocking
(`craft/verify.py:39`, `craft/gates.py:364`), so the difference is not cosmetic —
a reviewer has to be able to tell which kind they are looking at.

`apps/web/src/ui/toneMap.ts` keeps the matching glossary
(`ACCEPT_SEVERITY_CN`); `tests/unit/test_accept_severity_parity.py` reconciles
the two in both directions, and any severity the scanner reports that is not
declared here fails that gate rather than reaching the console as a raw token.
"""
from __future__ import annotations

from typing import Final

ACCEPT_FINDING_SEVERITIES: Final[frozenset[str]] = frozenset(
    {
        # Reported by agent/security_scanner.py's secret rules.
        "CRITICAL",
        "HIGH",
        "MEDIUM",
        "LOW",
        # Written by craft's own finding helpers as their defaults.
        "BLOCKER",
        "MAJOR",
    }
)

#: The two severities the acceptance gates actually block on.
BLOCKING_ACCEPT_SEVERITIES: Final[tuple[str, ...]] = ("CRITICAL", "HIGH")
