import sys

from craft.llm import LLMClient
from providers.base import LLMMessage, LLMResponse


class MockProvider:
    def __init__(self, streaming=True, content="hello world", usage=None):
        self.streaming = streaming
        self.content = content
        self.usage = usage or {
            "prompt_tokens": 21,
            "completion_tokens": 11,
            "reasoning_tokens": 4,
        }

    async def chat(self, messages, tools=None, tool_choice=None, response_format=None,
                   thinking=False, opts=None, timeout=180.0):
        return LLMResponse(content=self.content, usage=dict(self.usage), model="mock")

    async def chat_stream(self, messages, tools=None, thinking=False, opts=None,
                          timeout=180.0):
        for piece in ("hello", " ", "world"):
            yield LLMResponse(content=piece, model="mock")
        yield LLMResponse(content=None, usage=dict(self.usage), model="mock")

    def get_capabilities(self):
        return {"chat": True, "streaming": self.streaming}


def show(label, client):
    print("--- " + label + " ---")
    pieces = []
    for piece in client.stream_chat_sync(
        [LLMMessage(role="user", content="hi")], label=label
    ):
        pieces.append(piece)
        sys.stdout.write(piece)
        sys.stdout.flush()
    print()
    print("pieces:", pieces)
    print("last_stream_mode:", client.last_stream_mode)
    print("calls[-1][stream_mode]:", client.calls[-1].get("stream_mode"))
    usage = {k: v for k, v in client.calls[-1].items() if "tokens" in k or k == "charge"}
    print("usage:", usage)
    print("budget.used:", round(client.budget.used, 1))
    client.close()


show("native", LLMClient(provider=MockProvider(streaming=True)))
show("fallback", LLMClient(provider=MockProvider(streaming=False, content="one-shot reply")))
