"""Innovation capability first slices (计划书 §19.4-19.6).

Repository Digital Twin, Continuous Repair Queue and Learning from
Rejections as pure, deterministic kernels: no network, no Docker, no
global state. Persistence, scheduling and LLM-assisted clustering are
deliberately left to later slices (documented per module).
"""

from .digital_twin import (
    ApiEntry,
    DependencyEdge,
    ImpactEntry,
    MigrationEntry,
    RepositoryTwin,
    TwinModule,
    build_from_symbol_index,
    impact_estimate,
)
from .rejection_learning import (
    RejectionRecord,
    RejectionRule,
    build_eval_case,
    build_eval_cases,
    extract_rules,
    sanitize_record,
)
from .repair_queue import (
    DispatchPlan,
    RepairTicket,
    Severity,
    TicketSource,
    TicketStatus,
    apply_rate_limits,
    is_auto_eligible,
    plan_dispatch,
    priority_order,
)

__all__ = [
    "ApiEntry",
    "DependencyEdge",
    "DispatchPlan",
    "ImpactEntry",
    "MigrationEntry",
    "RejectionRecord",
    "RejectionRule",
    "RepairTicket",
    "RepositoryTwin",
    "Severity",
    "TicketSource",
    "TicketStatus",
    "TwinModule",
    "apply_rate_limits",
    "build_eval_case",
    "build_eval_cases",
    "build_from_symbol_index",
    "extract_rules",
    "impact_estimate",
    "is_auto_eligible",
    "plan_dispatch",
    "priority_order",
    "sanitize_record",
]
