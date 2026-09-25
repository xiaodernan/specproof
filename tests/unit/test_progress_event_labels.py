"""The progress stream's event names must be glossed in the UI, both ways.

The worker writes node/status literals into the Redis progress stream and the
timeline renders them through `apps/web/src/ui/stages.ts` and `StatusPill.tsx`.
An unregistered name is not an error: `stageLabel()` passes it through
verbatim, which is how the failure event came to be displayed as a raw job id
(job id was passed as the "stage"), and how every finished stage row showed
the bare token "COMPLETED".

This gate reads the real producers by parsing the source with `ast` (a moved
line or a renamed variable cannot hide a call site) and the real label maps by
parsing the TypeScript object literals, and reconciles them in BOTH
directions:

- produced but not glossed  -> the UI shows jargon to a user;
- glossed but not produced  -> the glossary rots into a list nobody maintains.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKER = REPO / "agent" / "worker.py"
GRAPH = REPO / "agent" / "graph.py"
STAGES_TS = REPO / "apps" / "web" / "src" / "ui" / "stages.ts"
STATUS_TSX = REPO / "apps" / "web" / "src" / "ui" / "StatusPill.tsx"

_FIELD_RE = re.compile(r'^\s*"?([A-Za-z_]\w*)"?\s*:', re.M)


def _string_literals(node: ast.AST) -> set[str]:
    """Every string literal in this expression, including both branches of a
    conditional (the worker picks a status with `A if parked else B`)."""
    found: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            found.add(sub.value)
    return found


def _progress_event_names() -> tuple[set[str], set[str]]:
    """(node names, status values) the worker writes into the stream."""
    tree = ast.parse(WORKER.read_text(encoding="utf-8"))
    nodes: set[str] = set()
    statuses: set[str] = set()
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        if getattr(call.func, "attr", "") != "xadd_progress":
            continue
        args = call.args
        if len(args) > 1:
            nodes |= _string_literals(args[1])
        if len(args) > 2:
            statuses |= _string_literals(args[2])
    return nodes, statuses


def _graph_node_names() -> set[str]:
    tree = ast.parse(GRAPH.read_text(encoding="utf-8"))
    names: set[str] = set()
    for call in ast.walk(tree):
        if (
            isinstance(call, ast.Call)
            and getattr(call.func, "attr", "") == "add_node"
            and call.args
        ):
            names |= _string_literals(call.args[0])
    return names


def _ts_object_keys(path: Path, export_prefix: str) -> set[str]:
    text = path.read_text(encoding="utf-8")
    _, _, rest = text.partition(export_prefix)
    body, _, _ = rest.partition("};")
    return set(_FIELD_RE.findall(body))


def test_every_event_the_worker_writes_has_a_chinese_gloss() -> None:
    nodes, statuses = _progress_event_names()
    labels = _ts_object_keys(STAGES_TS, "STAGE_LABELS: Record<string, string> = {")
    status_labels = _ts_object_keys(
        STATUS_TSX, "STATUS_LABELS: Record<string, string> = {"
    )
    assert nodes, "no xadd_progress call site found — the probe is broken"
    assert not nodes - labels, f"stream nodes without a gloss: {sorted(nodes - labels)}"
    missing = {s.upper() for s in statuses} - status_labels
    assert not missing, f"stream statuses without a gloss: {sorted(missing)}"


def test_every_graph_node_has_a_gloss() -> None:
    names = _graph_node_names()
    labels = _ts_object_keys(STAGES_TS, "STAGE_LABELS: Record<string, string> = {")
    assert len(names) >= 10, f"only {len(names)} add_node() sites parsed"
    assert not names - labels, f"pipeline nodes without a gloss: {sorted(names - labels)}"


def test_no_gloss_is_left_pointing_at_nothing() -> None:
    """The reverse direction: a glossary entry nobody emits is decay, not safety."""
    nodes, _statuses = _progress_event_names()
    labels = _ts_object_keys(STAGES_TS, "STAGE_LABELS: Record<string, string> = {")
    produced = nodes | _graph_node_names()
    assert not labels - produced, (
        "STAGE_LABELS entries emitted by neither the graph nor the worker: "
        f"{sorted(labels - produced)}"
    )


MYSQL = REPO / "storage" / "mysql.py"


def _row_status_vocabulary(path: Path) -> set[str]:
    """Every status the verification_jobs state machine can put on a row.

    Parsed from the ``_VALID_TRANSITIONS`` dict (keys ∪ values cover every
    status the machine can ever write) — a renamed constant or a new status
    row cannot hide from the probe.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    statuses: set[str] = set()
    for node in tree.body:
        # _VALID_TRANSITIONS is an annotated assignment (AnnAssign), so
        # both assignment shapes must be probed (Assign.targets / AnnAssign.target).
        target = node.targets[0] if isinstance(node, ast.Assign) else getattr(
            node, "target", None
        )
        if getattr(target, "id", "") == "_VALID_TRANSITIONS" and isinstance(
            node.value, ast.Dict
        ):
            statuses |= _string_literals(node.value)
    return statuses


def test_every_row_status_is_glossed_for_frame_echo_and_pills() -> None:
    """The lease frame echoes the row's status verbatim (#66), and every
    job-status pill renders through the same map — so the state machine's
    vocabulary must be fully glossed in STATUS_LABELS. Without this, a rare
    echo inside the CAS/read-back window (e.g. STALE, a legal RUNNING
    outcome) would show a user a raw token."""
    statuses = _row_status_vocabulary(MYSQL)
    assert statuses, "state-machine constants not found — the probe is broken"
    assert "STALE" in statuses, "vocabulary probe missed the dict values"
    status_labels = _ts_object_keys(
        STATUS_TSX, "STATUS_LABELS: Record<string, string> = {"
    )
    missing = statuses - status_labels
    assert not missing, f"row statuses without a gloss: {sorted(missing)}"
