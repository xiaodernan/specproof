"""devtools — deterministic developer tools ported from DevMind.

Submodules:
- quality: Python code-quality analysis (AST metrics, smells, 1-10 score)
- docs: deterministic Markdown doc generation (api / readme)
- archreview: import-graph architecture review (cycles, layers, hubs)

All tools are deterministic and offline: no LLM, no network, no side
effects. Python-only by design — other languages fail closed with an
explicit not_supported note, never guessed at.
"""

from devtools.archreview import review
from devtools.docs import generate
from devtools.quality import analyze

__all__ = ["analyze", "generate", "review"]
