"""Evidence package — Reports, Capsules, Certificates.

The Requirement-to-Evidence Matrix is built by the agent's build_matrix node
(agent/nodes/build_matrix.py) from real per-contract experiment results.
The old standalone matrix builder fabricated PASS for contracts without
findings and was removed — the matrix may only contain results an experiment
actually produced (PASS / FAIL / UNVERIFIED).
"""

from .certificate import MergeCertificate, issue_certificate
from .report import render_eval_report, render_verification_report

__all__ = [
    "render_verification_report",
    "render_eval_report",
    "MergeCertificate",
    "issue_certificate",
]
