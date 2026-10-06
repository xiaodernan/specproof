"""#174 — SSE event-kind vocabulary parity between producer and UI.

The agent console emits SSE frames whose `event:` field names the kind
(`plan`, `tool_call`, `tool_result`, `edit`, `gate`, `progress`, `model_output`).
The UI renders them through `eventKindLabel` in `apps/web/src/agent/util.ts`,
whose `EVENT_KIND_LABELS` constant is the canonical vocabulary.

Three things must hold:
  1. Every kind the backend emits has a UI label (no raw token leaks to the reader).
  2. Every UI label has a producer (no dead vocabulary).
  3. The `EVENT_TYPES` declaration in `api/agent_runtime.py` equals the producer set
     (convergence fence: if someone adds a new emit without updating EVENT_TYPES,
     or vice versa, this gate catches it).

Additionally, the `replay_gap` SSE frame (emitted when the stream catches up after
a gap) must NOT be rendered as a normal event row. The frontend's
`openAgentEventStream` now discriminates by shape: gap frames go to a separate
`onGap` callback, not the event list. This gate scans for consumers that still
push raw frames without shape checks.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RUNTIME = REPO / "api" / "agent_runtime.py"
CONSOLE = REPO / "api" / "routes" / "agent_console.py"
UTIL_TS = REPO / "apps" / "web" / "src" / "agent" / "util.ts"
API_TS = REPO / "apps" / "web" / "src" / "api.ts"
COMPONENTS_TSX = REPO / "apps" / "web" / "src" / "agent" / "components.tsx"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_event_types_from_console() -> set[str]:
    """Parse `EVENT_TYPES = (...)` from api/routes/agent_console.py."""
    src = _read(CONSOLE)
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "EVENT_TYPES":
                    if isinstance(node.value, ast.Tuple):
                        return {
                            elt.value
                            for elt in node.value.elts
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                        }
    return set()


def _extract_event_kind_labels_from_util() -> set[str]:
    """Parse `EVENT_KIND_LABELS = {...}` keys from util.ts."""
    src = _read(UTIL_TS)
    # Match: export const EVENT_KIND_LABELS: Record<string, string> = { ... }
    m = re.search(r"export\s+const\s+EVENT_KIND_LABELS\s*:\s*Record<string,\s*string>\s*=\s*\{([^}]+)\}", src)
    if not m:
        return set()
    body = m.group(1)
    # Extract keys: plan: "...", tool_call: "...", etc.
    keys = re.findall(r"(\w+)\s*:", body)
    return set(keys)


def _extract_produced_kinds_from_runtime() -> set[str]:
    """Scan all `_emit("kind", ...)` / `emit_event(..., "kind")` / `record_event(..., "kind")` calls."""
    src = _read(RUNTIME)
    tree = ast.parse(src)
    produced = set()

    class EmitVisitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            # _emit("kind", {...}) - method call
            if isinstance(node.func, ast.Attribute) and node.func.attr == "_emit":
                if node.args and isinstance(node.args[0], ast.Constant):
                    produced.add(node.args[0].value)
            # state.record_event(job_id, "kind", {...}) - method call
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "record_event":
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    produced.add(node.args[1].value)
            # emit_event(job_id, "kind", {...}) - function call
            elif isinstance(node.func, ast.Name) and node.func.id == "emit_event":
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    produced.add(node.args[1].value)
            # record_event(job_id, "kind", {...}) - function call
            elif isinstance(node.func, ast.Name) and node.func.id == "record_event":
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    produced.add(node.args[1].value)
            self.generic_visit(node)

    EmitVisitor().visit(tree)
    return produced


def _has_shape_discrimination_in_components() -> bool:
    """Check that components.tsx's SSE handler discriminates replay_gap by shape."""
    src = _read(COMPONENTS_TSX)
    # Look for: replayGap state and the gap callback in openAgentEventStream
    # The fix adds: const [replayGap, setReplayGap] = useState<AgentReplayGap | null>(null);
    # and passes: (gap) => { if (alive) setReplayGap(gap); }
    return "replayGap" in src and "setReplayGap" in src


def _api_passes_gap_separately() -> bool:
    """Check that api.ts's openAgentEventStream passes gap frames to onGap, not onEvent."""
    src = _read(API_TS)
    # Look for: if (type === "replay_gap") { onGap?.(...); return; }
    return "replay_gap" in src and "onGap" in src


def test_produced_kinds_are_subset_of_ui_labels() -> None:
    """Every kind the backend emits must have a UI label (no raw token leaks)."""
    produced = _extract_produced_kinds_from_runtime()
    ui_labels = _extract_event_kind_labels_from_util()
    assert produced, "no produced kinds found (parser broken?)"
    assert ui_labels, "no UI labels found (parser broken?)"
    leaked = produced - ui_labels
    assert not leaked, f"produced kinds without UI labels (raw token leak): {leaked}"


def test_ui_labels_are_subset_of_produced_kinds() -> None:
    """Every UI label must have a producer (no dead vocabulary)."""
    produced = _extract_produced_kinds_from_runtime()
    ui_labels = _extract_event_kind_labels_from_util()
    assert produced, "no produced kinds found (parser broken?)"
    assert ui_labels, "no UI labels found (parser broken?)"
    dead = ui_labels - produced
    assert not dead, f"UI labels without a producer (dead vocabulary): {dead}"


def test_event_types_declaration_equals_produced_kinds() -> None:
    """EVENT_TYPES in api/routes/agent_console.py must equal the actual producer set."""
    declared = _extract_event_types_from_console()
    produced = _extract_produced_kinds_from_runtime()
    assert declared, "EVENT_TYPES not found or empty (parser broken?)"
    assert produced, "no produced kinds found (parser broken?)"
    assert declared == produced, (
        f"EVENT_TYPES declaration drift: "
        f"declared={sorted(declared)}, produced={sorted(produced)}, "
        f"missing_from_declaration={sorted(produced - declared)}, "
        f"missing_from_production={sorted(declared - produced)}"
    )


def test_replay_gap_frames_are_shape_discriminated() -> None:
    """replay_gap SSE frames must not be rendered as normal event rows."""
    assert _api_passes_gap_separately(), (
        "api.ts openAgentEventStream does not pass replay_gap to onGap callback "
        "(gap frames will leak into event list and render as phantom rows)"
    )
    assert _has_shape_discrimination_in_components(), (
        "components.tsx useAgentJob does not handle onGap callback "
        "(replayGap state will not be tracked and disclosed)"
    )
