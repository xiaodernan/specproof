"""ProbeResult — immutable capability snapshot from a provider probe."""

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class ProbeResult:
    provider: str  # "openai_compatible"
    base_url: str
    model: str
    capabilities: dict = field(default_factory=dict)
    limits: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    probed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    CAPABILITY_KEYS = [
        "chat",
        "streaming",
        "json_output",
        "tool_calls",
        "strict_tool_calls",
        "thinking",
        "thinking_with_tools",
        "usage_reporting",
        "error_codes",
        "rate_limit_headers",
    ]

    def passed(self, capability: str) -> bool:
        return bool(self.capabilities.get(capability, False))

    def all_passed(self) -> bool:
        return all(self.capabilities.get(k, False) for k in self.CAPABILITY_KEYS)

    def summary(self) -> str:
        passed = sum(1 for k in self.CAPABILITY_KEYS if self.passed(k))
        total = len(self.CAPABILITY_KEYS)
        lines = [f"Probe {self.provider} @ {self.base_url} model={self.model}"]
        lines.append(f"  Result: {passed}/{total} capabilities passed")
        for k in self.CAPABILITY_KEYS:
            mark = "PASS" if self.passed(k) else "FAIL"
            lines.append(f"  [{mark}] {k}")
        if self.errors:
            lines.append("  Errors:")
            for e in self.errors:
                lines.append(f"    - {e}")
        return "\n".join(lines)
