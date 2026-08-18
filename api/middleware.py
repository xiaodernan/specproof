"""FastAPI middleware completions (J round): Request-ID + JSON payload limit.

Both middlewares are pure ASGI (no BaseHTTPMiddleware) so streaming
responses - the job progress SSE endpoint - are never buffered or broken,
and the request body can be bounded BEFORE routing/auth runs.

Ordering contract (see api/server.py): RequestIDMiddleware is the
outermost middleware (it must see every response, including errors from
deeper layers); PayloadLimitMiddleware runs before the auth/rate-limit
route dependencies so oversized bodies are rejected as 413 without ever
hitting application code.
"""

from __future__ import annotations

import json
import logging
import os
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.errors import PAYLOAD_TOO_LARGE, api_error_response
from observability.logging import request_id_var

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
DEFAULT_MAX_JSON_BYTES = 10 * 1024 * 1024  # 10 MiB

_JSON_METHODS = frozenset({"POST", "PUT", "PATCH"})
# Only the JSON API surface is limited; SSE (GET streams), static files and
# the SPA are never touched.
_JSON_PATH_PREFIXES = ("/api/", "/jobs", "/webhooks")


class RequestIDMiddleware:
    """Read X-Request-ID or generate one; echo it on the response.

    The id is also set on request.state.request_id for handlers and on the
    observability request_id_var context variable, so every structured log
    line emitted while the request is being processed carries the same
    request_id field (observability JsonFormatter convention).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        request_id = headers.get(REQUEST_ID_HEADER, "").strip() or uuid.uuid4().hex[:16]
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        token = request_id_var.set(request_id)
        logger.info(
            "request %s %s", scope.get("method"), scope.get("path"),
            extra={"request_id": request_id},
        )
        try:
            async def send_with_request_id(message: Message) -> None:
                if message["type"] == "http.response.start":
                    response_headers = MutableHeaders(scope=message)
                    if not response_headers.get(REQUEST_ID_HEADER):
                        response_headers.append(REQUEST_ID_HEADER, request_id)
                await send(message)

            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_var.reset(token)


class PayloadLimitMiddleware:
    """Reject oversized JSON request bodies with 413 before auth/routing.

    Scope: POST/PUT/PATCH with an application/json content type on the JSON
    API surface (/api/, /jobs, /webhooks). The limit comes from
    SPECPROOF_MAX_JSON_BYTES (default 10 MiB). SSE responses are GET streams
    and are never affected.
    """

    def __init__(self, app: ASGIApp, max_bytes: int | None = None) -> None:
        self.app = app
        self.default_max_bytes = max_bytes if max_bytes is not None else DEFAULT_MAX_JSON_BYTES

    def _current_limit(self) -> int:
        raw = os.getenv("SPECPROOF_MAX_JSON_BYTES", "").strip()
        if not raw:
            return self.default_max_bytes
        try:
            return int(raw)
        except ValueError:
            logger.warning(
                "SPECPROOF_MAX_JSON_BYTES=%r is not an integer; using default %d",
                raw,
                self.default_max_bytes,
            )
            return self.default_max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("method") not in _JSON_METHODS:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if not any(path.startswith(prefix) for prefix in _JSON_PATH_PREFIXES):
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        content_type = headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            await self.app(scope, receive, send)
            return
        limit = self._current_limit()
        declared = headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > limit:
                    await self._send_413(send, limit)
                    return
            except ValueError:
                pass  # malformed Content-Length: fall through to counting
        body = bytearray()
        total = 0
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return  # client is gone; nothing to answer
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > limit:
                await self._send_413(send, limit)
                return
            body.extend(chunk)
            more_body = bool(message.get("more_body", False))
        delivered = False

        async def replay_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)

    async def _send_413(self, send: Send, limit: int) -> None:
        # §8.1: the 413 body is the stable error envelope (PAYLOAD_TOO_LARGE)
        # with the legacy detail string preserved; the request_id comes from
        # the RequestIDMiddleware context (this middleware sends directly, so
        # the global exception handler in api/server.py never sees it).
        detail = (
            f"Request body exceeds the JSON payload limit of "
            f"{limit} bytes (SPECPROOF_MAX_JSON_BYTES)"
        )
        body = api_error_response(
            413, PAYLOAD_TOO_LARGE, detail, request_id_var.get() or None
        )
        payload = json.dumps(body).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("ascii")),
                (b"connection", b"close"),
            ],
        })
        await send({"type": "http.response.body", "body": payload})
