"""Investigator lane regression — a fake model client must never yield an
'ok' outcome without token accounting."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from craft.investigators import _llm_execute_factory


class _FakeClient:
    def __init__(self, resp: Any) -> None:
        self.resp = resp

    async def chat(self, _messages: Any, label: str = "", kind: str | None = None, timeout: Any = None):
        return self.resp


class _FakeSpec:
    def __init__(self, role: str) -> None:
        self.name = f"investigate_{role}"
        self.role = role
        self.task = "sample question"
        self.timeout = None


class _FakeContext:
    workspace = "."


@pytest.mark.asyncio
async def test_ok_path_takes_tokens_from_the_wire() -> None:
    resp = SimpleNamespace(
        content="规则在 job=api 的 up 持续为 0 时触发 critical；evidence enclosed",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    executor = await _llm_execute_factory(_FakeClient(resp), ".")
    result = await executor(_FakeSpec("tester"), _FakeContext())
    assert result.outcome == "ok"
    assert result.tokens == 15
    assert result.findings, "findings may not be empty on the ok path"


@pytest.mark.asyncio
async def test_provider_unavailable_lands_honestly_not_as_unbound() -> None:
    class _BoomClient(_FakeClient):
        async def chat(self, *args: Any, **kwargs: Any):  # noqa: ANN001
            raise RuntimeError("boom")

    executor = await _llm_execute_factory(_BoomClient(None), ".")
    result = await executor(_FakeSpec("explorer"), _FakeContext())
    assert result.outcome == "error"
    assert "RuntimeError" in result.findings[0]["claim"]
    assert result.tokens == 0
