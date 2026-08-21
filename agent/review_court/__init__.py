"""Review Court package.

agent/review_court/policy.py — deterministic policy layer
(policy_recalculate: severity/status from evidence, confidence bounds,
Base/Head runtime comparison, BLOCKER six-conditions, preexisting-defect
rule). agent/nodes/review_court.py — the node orchestrating candidates,
the optional injected model defense layer and the policy layer.
"""
