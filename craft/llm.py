"""M2 LLM client (design doc §4.8 + 附录 F): provider wrapper, token
budget gate and an in-memory reasoning journal.

Every LLM call goes through LLMClient.chat()/chat_sync(); streaming
(卷 XXI §21.3) goes through stream_chat_sync() or the per-client
stream_hook:

- the provider (providers/openai_compatible.py) is built lazily
  (probe_on_init=False): the capability probe runs on the first real call;
- before the call the TokenBudget gate checks the estimated prompt charge
  (providers/budget.py); after the call the actual usage is recorded;
  an overrun raises BudgetExceeded — catchable, never silent;
- reasoning_content (ADR-017) goes ONLY into the in-memory reasoning
  journal (tagged with job_id/step_id) and in-memory statistics; it never
  reaches checkpoint.json / report.json / memory.json / any artifact, log
  lines carry token counts, never reasoning text, and the stream hook
  receives content chunks only;
- stream mode is honest and on record: every streamed call's stats entry
  carries stream_mode="native"|"fallback", and LLMClient.last_stream_mode
  reports the last call's mode. Native streaming aggregates the chunk
  usage into budget.record + stats exactly once; a fallback runs the
  regular non-streaming chat() path and yields the final content once.
  (Native chat_stream has no response_format slot in the provider
  contract, so --stream drops response_format for streamed calls; the
  JSON contract stays enforced by the prompt template + tolerant parsing.)

The token limit comes from --budget-tokens / CRAFT_TOKEN_BUDGET and
defaults to 500000 (the M2 LLM gate; the M1 plan-allocation default in
craft/budget.py is a separate planning-era figure).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import threading
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, cast

from providers.base import LLMMessage, LLMResponse, ModelProvider
from providers.budget import BudgetExceeded as BudgetExceeded
from providers.budget import TokenBudget
from providers.openai_compatible import OpenAICompatibleProvider
from providers.prompt_templates import THINKING_MODE_ENV, resolve_thinking

DEFAULT_LLM_TOKEN_BUDGET = 500_000
SYNC_CALL_TIMEOUT = 900.0  # generous: first call includes the lazy capability probe
LOGGER = logging.getLogger("craft.llm")


class LLMUnavailableError(RuntimeError):
    """No usable LLM route: missing key, placeholder key, or provider failure."""


class LLMClient:
    """Provider wrapper + token budget + in-memory reasoning journal.

    chat() is the async core; chat_sync() runs it on a private event-loop
    thread so the synchronous planner/loop can call the model without
    owning an event loop. The loop thread starts lazily on the first
    chat_sync() call; tests with a stub provider may call chat() directly.
    """

    def __init__(
        self,
        *,
        provider: ModelProvider | None = None,
        token_budget: int | None = None,
        cost_weights: dict[str, float] | None = None,
        timeout: float = 180.0,
        max_retries: int | None = None,
        job_id: str = "",
        stream_hook: Callable[[str], None] | None = None,
    ) -> None:
        limit = (
            token_budget
            if token_budget is not None
            else _env_int("CRAFT_TOKEN_BUDGET", DEFAULT_LLM_TOKEN_BUDGET)
        )
        self.budget = TokenBudget(limit_tokens=float(limit), cost_weights=cost_weights)
        self._provider = provider
        self.timeout = timeout
        self.max_retries = max_retries
        self.job_id = job_id
        # Optional content-delta sink (卷 XXI §21.3): when set and the
        # provider supports streaming, chat() streams natively and feeds
        # every content chunk to this hook (reasoning_content never goes
        # through — ADR-017). None keeps the legacy non-streaming path.
        self.stream_hook = stream_hook
        # Honest per-call mode annotation: "native" | "fallback" | "" (no
        # streaming requested). Set by chat()/stream_chat_sync().
        self.last_stream_mode = ""
        # In-memory statistics — numeric only, safe to persist later.
        self.calls: list[dict[str, Any]] = []
        # In-memory reasoning journal — ADR-017: NEVER persisted anywhere.
        self.reasoning_journal: list[dict[str, Any]] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._provider_error: str = ""

    # -- availability -----------------------------------------------------

    @property
    def available(self) -> bool:
        if self._provider is not None:
            return True
        key = os.getenv("LLM_API_KEY", "").strip()
        return bool(key) and key != "replace_me"

    def unavailable_reason(self) -> str:
        if self._provider is not None:
            return ""
        key = os.getenv("LLM_API_KEY", "").strip()
        if not key:
            return "LLM_API_KEY 未设置"
        if key == "replace_me":
            return "LLM_API_KEY 为占位符 'replace_me'"
        return ""

    def _get_provider(self) -> ModelProvider:
        if self._provider is not None:
            return self._provider
        if self._provider_error:
            raise LLMUnavailableError(self._provider_error)
        if not self.available:
            raise LLMUnavailableError("LLM unavailable: " + self.unavailable_reason())
        try:
            self._provider = OpenAICompatibleProvider(
                probe_on_init=False,
                max_retries=self.max_retries,
                timeout=self.timeout,
            )
        except (ValueError, OSError) as exc:
            self._provider_error = f"LLM provider 构造失败: {exc}"
            raise LLMUnavailableError(self._provider_error) from exc
        return self._provider

    # -- core call --------------------------------------------------------

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        label: str,
        job_id: str = "",
        step_id: str = "",
        thinking: bool = False,
        response_format: dict[str, Any] | None = None,
        estimated_prompt_tokens: int = 0,
        timeout: float | None = None,
    ) -> LLMResponse:
        """One budget-gated LLM call with reasoning journaling.

        When stream_hook is set and the provider supports streaming
        (capability probe), the call streams natively: every content
        chunk goes to the hook, usage is aggregated into budget.record +
        stats exactly once, and the call entry is annotated
        stream_mode="native". A hook with a non-streaming provider runs
        the regular path and is annotated stream_mode="fallback" — the
        hook never fires (honest fallback, no faked deltas).

        BudgetExceeded propagates to the caller (planner degrades to the
        rule plan; the loop turns it into an honest FAILED).
        LLMUnavailableError propagates when no usable route exists.
        """
        provider = self._get_provider()
        self.budget.check(estimated_prompt_tokens, label=label)
        wants_stream = self.stream_hook is not None
        if wants_stream and await self._stream_capability(provider):
            return await self._chat_streaming(
                provider,
                messages,
                label=label,
                job_id=job_id,
                step_id=step_id,
                thinking=thinking,
                timeout=timeout if timeout is not None else self.timeout,
                on_chunk=self.stream_hook,
            )
        try:
            response = await provider.chat(
                messages,
                response_format=response_format,
                thinking=thinking,
                timeout=timeout if timeout is not None else self.timeout,
            )
        except LLMUnavailableError:
            raise
        except Exception as exc:
            raise LLMUnavailableError(f"LLM 调用失败: {type(exc).__name__}: {exc}") from exc
        entry = self.budget.record(response.usage, label=label)  # may raise BudgetExceeded
        stream_mode = "fallback" if wants_stream else ""
        self._journal(
            response,
            entry,
            label=label,
            job_id=job_id or self.job_id,
            step_id=step_id,
            stream_mode=stream_mode,
        )
        if wants_stream:
            self.last_stream_mode = "fallback"
        LOGGER.info(
            "craft llm call",
            extra={
                "craft_llm": {
                    "label": label,
                    "job_id": job_id or self.job_id,
                    "step_id": step_id,
                    "prompt_tokens": entry["prompt_tokens"],
                    "completion_tokens": entry["completion_tokens"],
                    "reasoning_tokens": entry["reasoning_tokens"],
                    "charge": entry["charge"],
                }
            },
        )
        return response

    def chat_sync(
        self,
        messages: list[LLMMessage],
        *,
        label: str,
        job_id: str = "",
        step_id: str = "",
        thinking: bool = False,
        response_format: dict[str, Any] | None = None,
        estimated_prompt_tokens: int = 0,
        timeout: float | None = None,
    ) -> LLMResponse:
        """Synchronous facade: run chat() on the client's private loop thread."""
        self._ensure_loop()
        loop = self._loop
        if loop is None:
            raise LLMUnavailableError("LLMClient 事件循环初始化失败")
        future = asyncio.run_coroutine_threadsafe(
            self.chat(
                messages,
                label=label,
                job_id=job_id,
                step_id=step_id,
                thinking=thinking,
                response_format=response_format,
                estimated_prompt_tokens=estimated_prompt_tokens,
                timeout=timeout,
            ),
            loop,
        )
        try:
            return future.result(timeout=SYNC_CALL_TIMEOUT)
        except (BudgetExceeded, LLMUnavailableError):
            raise
        except TimeoutError as exc:
            raise LLMUnavailableError(
                f"LLM 调用超时 ({SYNC_CALL_TIMEOUT:g}s): {exc}"
            ) from exc
        except Exception as exc:
            raise LLMUnavailableError(
                f"LLM 同步桥接失败: {type(exc).__name__}: {exc}"
            ) from exc

    def stream_chat_sync(
        self,
        messages: list[LLMMessage],
        *,
        label: str,
        job_id: str = "",
        step_id: str = "",
        thinking: bool = False,
        response_format: dict[str, Any] | None = None,
        estimated_prompt_tokens: int = 0,
        timeout: float | None = None,
    ) -> Iterator[str]:
        """Streaming facade (卷 XXI §21.3): a generator of content deltas.

        native — the provider streams: every non-empty chunk.content is
                 yielded as it arrives; at the end the aggregated usage is
                 recorded through budget.record + the stats journal
                 exactly once, and the call entry carries
                 stream_mode="native".
        fallback — no usable key, or the capability probe reports no
                 streaming: the regular chat() path runs once and the
                 final content is yielded as a single piece; the call
                 entry carries stream_mode="fallback" (honest annotation,
                 no faked deltas).

        self.last_stream_mode reports the mode of the most recent call.
        BudgetExceeded / LLMUnavailableError propagate from the iteration
        (the generator never swallows them).
        """
        self._ensure_loop()
        loop = self._loop
        if loop is None:
            raise LLMUnavailableError("LLMClient 事件循环初始化失败")
        pending: queue.Queue[tuple[str, object]] = queue.Queue()

        async def _produce() -> None:
            try:
                if not self.available:
                    raise LLMUnavailableError("LLM unavailable: " + self.unavailable_reason())
                provider = self._get_provider()
                self.budget.check(estimated_prompt_tokens, label=label)
                if await self._stream_capability(provider):
                    await self._chat_streaming(
                        provider,
                        messages,
                        label=label,
                        job_id=job_id,
                        step_id=step_id,
                        thinking=thinking,
                        timeout=timeout if timeout is not None else self.timeout,
                        on_chunk=lambda piece: pending.put(("chunk", piece)),
                    )
                    pending.put(("done", "native"))
                    return
                response = await self.chat(
                    messages,
                    label=label,
                    job_id=job_id,
                    step_id=step_id,
                    thinking=thinking,
                    response_format=response_format,
                    estimated_prompt_tokens=0,  # gate already checked above
                    timeout=timeout,
                )
                self.calls[-1]["stream_mode"] = "fallback"
                self.last_stream_mode = "fallback"
                content = response.content or ""
                if content:
                    pending.put(("chunk", content))
                pending.put(("done", "fallback"))
            except BaseException as exc:  # noqa: BLE001 — re-raised in the consumer
                pending.put(("error", exc))

        future = asyncio.run_coroutine_threadsafe(_produce(), loop)
        try:
            while True:
                try:
                    kind, payload = pending.get(timeout=SYNC_CALL_TIMEOUT)
                except queue.Empty as exc:
                    raise LLMUnavailableError(
                        f"LLM 流式调用超时 ({SYNC_CALL_TIMEOUT:g}s): {exc}"
                    ) from exc
                if kind == "chunk":
                    yield str(payload)
                    continue
                if kind == "done":
                    return
                if isinstance(payload, BaseException):
                    raise payload
                raise LLMUnavailableError(f"LLM 流式调用失败: {payload!r}")
        finally:
            future.cancel()

    async def _stream_capability(self, provider: ModelProvider) -> bool:
        """Does the provider stream? Asks get_capabilities() when a
        snapshot exists (test stubs); otherwise runs the provider's lazy
        probe via run_probe() (OpenAICompatibleProvider caches the result
        itself). Probe failures mean no streaming — the caller falls back,
        and the provider reports its own honest error on the next call.
        """
        try:
            caps = provider.get_capabilities()
        except Exception:
            caps = None
        if isinstance(caps, dict):
            return bool(caps.get("streaming"))
        probe_fn = getattr(provider, "run_probe", None)
        if not callable(probe_fn):
            return False
        try:
            result = await probe_fn()
        except Exception:
            return False
        result_caps = getattr(result, "capabilities", None)
        return bool(isinstance(result_caps, dict) and result_caps.get("streaming"))

    async def _chat_streaming(
        self,
        provider: ModelProvider,
        messages: list[LLMMessage],
        *,
        label: str,
        job_id: str,
        step_id: str,
        thinking: bool,
        timeout: float,
        on_chunk: Callable[[str], None] | None,
    ) -> LLMResponse:
        """Native streaming core shared by chat() and stream_chat_sync().

        The caller must already have run budget.check(). Content deltas
        go to on_chunk (reasoning_content stays in memory — ADR-017);
        per-chunk usage/reasoning/model are aggregated; afterwards the
        call is recorded through budget.record + _journal exactly once
        and annotated stream_mode="native".
        """
        chunks: list[str] = []
        usage: dict[str, Any] = {}
        reasoning_parts: list[str] = []
        model = ""
        try:
            # The ModelProvider ABC declares chat_stream with async def,
            # which mypy reads as a coroutine; the real implementations are
            # async generators, so the call yields an async iterator directly.
            stream = cast(
                AsyncIterator[LLMResponse],
                provider.chat_stream(messages, thinking=thinking, timeout=timeout),
            )
            async for piece in stream:
                content = piece.content
                if content:
                    chunks.append(content)
                    if on_chunk is not None:
                        on_chunk(content)
                if piece.reasoning_content:
                    reasoning_parts.append(piece.reasoning_content)
                if piece.usage:
                    usage.update(dict(piece.usage))
                if piece.model:
                    model = piece.model
        except LLMUnavailableError:
            raise
        except Exception as exc:
            raise LLMUnavailableError(
                f"LLM 流式调用失败: {type(exc).__name__}: {exc}"
            ) from exc
        response = LLMResponse(
            content="".join(chunks),
            reasoning_content="".join(reasoning_parts) or None,
            usage=usage,
            finish_reason="stop",
            model=model,
        )
        entry = self.budget.record(usage, label=label)  # may raise BudgetExceeded
        self._journal(
            response,
            entry,
            label=label,
            job_id=job_id or self.job_id,
            step_id=step_id,
            stream_mode="native",
        )
        self.last_stream_mode = "native"
        LOGGER.info(
            "craft llm stream call",
            extra={
                "craft_llm": {
                    "label": label,
                    "job_id": job_id or self.job_id,
                    "step_id": step_id,
                    "prompt_tokens": entry["prompt_tokens"],
                    "completion_tokens": entry["completion_tokens"],
                    "reasoning_tokens": entry["reasoning_tokens"],
                    "charge": entry["charge"],
                    "stream_mode": "native",
                }
            },
        )
        return response

    # -- loop-thread plumbing ---------------------------------------------

    def _ensure_loop(self) -> None:
        if self._loop is not None:
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="craft-llm-loop", daemon=True
        )
        self._thread.start()

    def close(self) -> None:
        if self._loop is None:
            return
        provider = self._provider
        if provider is not None and hasattr(provider, "close"):
            with suppress(Exception):
                asyncio.run_coroutine_threadsafe(provider.close(), self._loop).result(
                    timeout=30.0
                )
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=10.0)
        self._loop.close()
        self._loop = None
        self._thread = None

    # -- journal / stats ----------------------------------------------------

    def _journal(
        self,
        response: LLMResponse,
        entry: dict[str, Any],
        *,
        label: str,
        job_id: str,
        step_id: str,
        stream_mode: str = "",
    ) -> None:
        call_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "label": label,
            "job_id": job_id,
            "step_id": step_id,
            "model": response.model or "",
            "prompt_tokens": entry["prompt_tokens"],
            "completion_tokens": entry["completion_tokens"],
            "reasoning_tokens": entry["reasoning_tokens"],
            "prompt_cache_hit_tokens": entry["prompt_cache_hit_tokens"],
            "prompt_cache_miss_tokens": entry["prompt_cache_miss_tokens"],
            "charge": entry["charge"],
        }
        if stream_mode:
            call_entry["stream_mode"] = stream_mode
        self.calls.append(call_entry)
        reasoning = response.reasoning_content
        if reasoning:
            self.reasoning_journal.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                    "label": label,
                    "job_id": job_id,
                    "step_id": step_id,
                    "reasoning_len": len(reasoning),
                    "reasoning_content": reasoning,
                }
            )

    def stats_report(self) -> dict[str, Any]:
        """Serializable statistics — token counts only, NEVER reasoning text."""
        prompt = sum(int(entry["prompt_tokens"]) for entry in self.calls)
        completion = sum(int(entry["completion_tokens"]) for entry in self.calls)
        reasoning = sum(int(entry["reasoning_tokens"]) for entry in self.calls)
        cache_hit = sum(int(entry["prompt_cache_hit_tokens"]) for entry in self.calls)
        cache_miss = sum(int(entry["prompt_cache_miss_tokens"]) for entry in self.calls)
        return {
            "available": self.available,
            "calls": len(self.calls),
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "reasoning_tokens": reasoning,
            "prompt_cache_hit_tokens": cache_hit,
            "prompt_cache_miss_tokens": cache_miss,
            "reasoning_journal_entries": len(self.reasoning_journal),
            "budget": {
                "limit_tokens": self.budget.limit_tokens,
                "used": self.budget.used,
                "remaining": self.budget.remaining,
            },
            "calls_detail": list(self.calls),
        }


def resolve_craft_thinking(task: str, mode: str | None = None) -> bool:
    """Thinking switch for craft tasks — resolve_thinking() is the single
    authority, with one craft policy on top: under the default plan_only
    mode the diagnostic repair call stays thinking-OFF (plan/judge keep
    their reasoning tier). Under "auto" the diagnose template's own
    thinking_on flag applies.
    """
    effective = mode if mode is not None else os.getenv(THINKING_MODE_ENV, "plan_only")
    if task == "diagnose" and effective == "plan_only":
        return False
    return resolve_thinking(task, mode=effective)


def extract_json_object(text: str) -> Any:
    """Parse a model reply into a JSON object (fence-tolerant, honest).

    Raises json.JSONDecodeError / ValueError when the reply is not JSON —
    callers decide the degradation path, never fake a result.
    """
    fence = chr(96) * 3
    stripped = text.strip()
    if stripped.startswith(fence):
        stripped = stripped.strip(chr(96))
        newline = stripped.find("\n")
        if newline != -1 and stripped[:newline].strip().lower() in ("json", ""):
            stripped = stripped[newline + 1 :]
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(stripped[start : end + 1])


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise LLMUnavailableError(f"环境变量 {name}={raw!r} 不是整数") from exc
    if value <= 0:
        raise LLMUnavailableError(f"环境变量 {name}={value} 必须为正整数")
    return value
