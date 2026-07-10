"""ModelProvider abstract base class.

All agent nodes use this interface exclusively.
No node imports openai directly.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict] | None = None


@dataclass
class LLMResponse:
    content: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    finish_reason: str = "stop"
    model: str = ""
    reasoning_content: str | None = None


class ModelProvider(ABC):
    """Unified interface for all LLM calls.

    Implemented by OpenAICompatibleProvider.
    All nodes call chat() / chat_stream() through this ABC.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        response_format: dict | None = None,
        thinking: bool = False,
        timeout: float = 180.0,
    ) -> LLMResponse:
        """Send a chat completion request. Non-streaming."""

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[LLMMessage],
        tools: list[dict] | None = None,
        thinking: bool = False,
        timeout: float = 180.0,
    ) -> AsyncIterator[LLMResponse]:
        """Send a streaming chat completion request."""

    @abstractmethod
    def get_capabilities(self) -> dict:
        """Return probed capabilities dict.

        Keys: chat, streaming, json_output, tool_calls,
              strict_tool_calls, thinking, thinking_with_tools,
              usage_reporting, error_codes, rate_limit_headers
        """
