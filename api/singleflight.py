"""Process-local single-flight coalescing for public LLM lanes.

The owner's worry is real: parallel sessions striking a cold fingerprint all
miss the Redis cache at once, so N sessions make N model calls and the cache
'looks' cold. One instance per lane merges same-key misses: the first caller
becomes the leader and runs the loader; the rest await the same future.

Cross-process coalescing is left to the shared Redis fingerprint cache — this
is deliberately process-local. Pure asyncio: no threads, no locks, nothing
that blocks the event loop.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine


class SingleFlight:
    """Coalesce concurrent misses on the same key into ONE loader call."""

    def __init__(self) -> None:
        self._futures: dict[str, asyncio.Future] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    async def run(
        self,
        key: str,
        loader: Callable[[], Coroutine[Any, Any, Any]],
    ) -> Any:
        loop = asyncio.get_running_loop()
        # A future belongs to the loop that created it. TestClients and some
        # ASGI hosts run different requests on different loops; a future from
        # another loop cannot be awaited here, so treat it as no flight.
        if self._loop is not loop:
            self._futures.clear()
            self._loop = loop
        inflight = self._futures.get(key)
        if inflight is not None and not inflight.done():
            return await asyncio.shield(inflight)
        future: asyncio.Future = loop.create_future()
        self._futures[key] = future
        try:
            value = await loader()
        except BaseException as exc:  # noqa: BLE001 - every waiter shares the honest failure
            if not future.done():
                future.set_exception(exc)
                # Mark retrieved on the leader's own behalf: with no joiners,
                # asyncio would warn about an unconsumed future exception.
                future.exception()
            raise
        else:
            if not future.done():
                future.set_result(value)
            return value
        finally:
            # Drop only our own entry; a later leader may have replaced it.
            if self._futures.get(key) is future:
                self._futures.pop(key, None)
