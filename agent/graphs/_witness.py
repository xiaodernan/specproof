"""Shared witness-lane nodes for the StateGraph family.

Several witness graphs end their chain with a ``verdict`` node that merely
carries the state forward — the verdict is chosen upstream (by strike/search),
and this node exists so every chain reads intake → strike → verdict → report
→ END. One implementation, one inspectable identity; a copy per lane would
drift and would not be the same verifier.
"""
from __future__ import annotations

from typing import Any


def verdict_node(state: Any) -> Any:
    return state
