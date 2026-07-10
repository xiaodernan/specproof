"""LLM Provider abstraction for SpecProof Phase 0.

All agent nodes depend only on ModelProvider, never directly on OpenAI SDK.
This enables provider-agnostic verification and gateway capability probing.
"""

from .base import ModelProvider
from .capability_probe import CapabilityProbe
from .openai_compatible import OpenAICompatibleProvider
from .probe_result import ProbeResult

__all__ = [
    "ModelProvider",
    "CapabilityProbe",
    "OpenAICompatibleProvider",
    "ProbeResult",
]
