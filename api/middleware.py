"""FastAPI middleware completions: Request-ID, tenant auth, JSON payload limit.

Request-ID and PayloadLimit are pure ASGI (no BaseHTTPMiddleware) so
streaming responses — the job progress SSE endpoint — are never buffered or
broken, and the request body can be bounded BEFORE routing/auth runs.

TenantAuthMiddleware (industrialization phase 1,
docs/architecture/MULTI_TENANT_DESIGN.md §4) is the auth dependency
injection point: it parses Authorization (Bearer sp_* or OIDC JWT) into a
unified principal on request.state, enforces the §2 RBAC matrix, answers
cross-tenant job reads with 404 + audit(attempted_tenant), and publishes
the tenant scope contextvar consumed by the repository layer. It is
INERT unless auth is explicitly enabled (SPECPROOF_AUTH_ENABLED=true or
OIDC_ISSUER set) — the single-tenant deployment stays byte-identical.

Ordering contract (see api/server.py): RequestIDMiddleware is the
outermost middleware; TenantAuthMiddleware runs inside it but before
PayloadLimitMiddleware, so unauthenticated oversized bodies are rejected
as 401 before any body is buffered, and its own error envelopes carry the
request id.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import TYPE_CHECKING

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.errors import (
    AUTH_REQUIRED,
    JOB_NOT_FOUND,
    PAYLOAD_TOO_LARGE,
    TENANT_FORBIDDEN,
    api_error_response,
)
from observability.logging import request_id_var

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
DEFAULT_MAX_JSON_BYTES = 10 * 1024 * 1024  # 10 MiB

# ── Tenant auth (industrialization phase 1) ────────────────────────────────

#: Paths that never need a bearer credential, even in tenant mode.
_TENANT_OPEN_PREFIXES = (
    "/health",
    "/metrics",
    "/dashboard",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/assets",
    "/auth/oidc/",
    "/auth/config",
)
#: Paths under which a bearer credential is REQUIRED in tenant mode.
_TENANT_PROTECTED_PREFIXES = ("/jobs", "/agent", "/api/", "/auth/")
#: GitHub webhooks authenticate with their own HMAC secret (§webhooks).
_TENANT_EXEMPT_PREFIXES = ("/webhooks",)

#: SSE endpoints cannot send headers; the bearer token rides ?key= exactly
#: like the legacy X-API-Key SSE pattern in apps/web/src/api.ts.
_SSE_SUFFIXES = ("/progress", "/events")

_JOB_ID_RE = re.compile(r"^/(?:api/v1/)?jobs/([^/]+)")

if TYPE_CHECKING:
    from api.identity.principal import Principal

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


class TenantAuthMiddleware:
    """Multi-tenant auth: Bearer sp_*/OIDC → principal + RBAC + isolation.

    Pure ASGI, inert unless auth is enabled. When enabled it:
      1. requires a valid Bearer credential on protected API paths
         (missing/invalid → 401 AUTH_REQUIRED envelope);
      2. enforces the RBAC matrix (§2) → 403 TENANT_FORBIDDEN envelope;
      3. refuses cross-tenant job reads with 404 JOB_NOT_FOUND (never 403 —
         no existence leak) and records the attempt with attempted_tenant;
      4. injects request.state.principal and the repository-layer tenant
         scope contextvar for tenant-filtered queries.

    SSE endpoints may carry the token as ?key=/?api_key= (EventSource
    cannot set headers) — the same convention as the legacy API key.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        from api.identity.authn import authenticate_bearer
        from api.identity.config import auth_enabled
        from api.identity.principal import classify_request, principal_allowed
        from storage.tenant_scope import TENANT_SCOPE_VAR, TenantScope

        if not auth_enabled():
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        method = scope.get("method", "GET")
        if method == "OPTIONS" or path.startswith(_TENANT_EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return
        if any(path.startswith(prefix) for prefix in _TENANT_OPEN_PREFIXES):
            await self.app(scope, receive, send)
            return
        if not any(path.startswith(prefix) for prefix in _TENANT_PROTECTED_PREFIXES):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        authorization = headers.get("authorization", "")
        if not authorization and path.endswith(_SSE_SUFFIXES):
            # EventSource cannot set headers; token rides the query string.
            query_bytes = scope.get("query_string", b"")
            query = (
                query_bytes.decode("latin-1")
                if isinstance(query_bytes, bytes)
                else str(query_bytes)
            )
            token_from_query = self._token_from_query(query)
            if token_from_query:
                authorization = "Bearer " + token_from_query
        try:
            principal = authenticate_bearer(authorization)
        except Exception:  # noqa: BLE001 — fail closed, never a 500 oracle
            principal = None
        if principal is None:
            await self._send_error(
                send, scope, 401, AUTH_REQUIRED,
                "Missing or invalid bearer credentials",
            )
            return

        resource_action = classify_request(method, path)
        if resource_action is not None and not principal_allowed(
            principal, resource_action.resource, resource_action.action
        ):
            await self._send_error(
                send, scope, 403, TENANT_FORBIDDEN,
                (
                    f"role {sorted(principal.roles)} may not "
                    f"{resource_action.action} on {resource_action.resource}"
                ),
            )
            return

        if not self._cross_tenant_allowed(principal, path):
            await self._send_error(
                send, scope, 404, JOB_NOT_FOUND, "Job not found",
            )
            return

        state = scope.setdefault("state", {})
        state["principal"] = principal
        tenant_scope = TenantScope(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            roles=principal.roles,
        )
        token = TENANT_SCOPE_VAR.set(tenant_scope)
        try:
            await self.app(scope, receive, send)
        finally:
            TENANT_SCOPE_VAR.reset(token)

    @staticmethod
    def _token_from_query(query_string: str) -> str:
        if not query_string:
            return ""
        try:
            from urllib.parse import parse_qs

            parsed = parse_qs(query_string)
            return (parsed.get("key") or parsed.get("api_key") or [""])[0]
        except ValueError:
            return ""

    def _cross_tenant_allowed(self, principal: Principal, path: str) -> bool:
        """True unless the path reads a job owned by another tenant.

        Only jobs with an explicit tenant_id are isolated; legacy
        NULL-tenant rows stay shared. Auditors keep the cross-tenant view
        (§2). The probe is best-effort — the repository-layer scoping in
        storage/mysql.py remains the primary enforcement.
        """
        if "auditor" in principal.roles:
            return True
        match = _JOB_ID_RE.match(path)
        if match is None:
            return True
        job_id = match.group(1)
        try:
            from storage.mysql import MySQLStore

            owner = MySQLStore().get_job_tenant(job_id)
        except Exception:  # noqa: BLE001 — probe is advisory
            return True
        if owner is None or owner == principal.tenant_id:
            return True
        try:
            from storage.mysql import MySQLStore

            MySQLStore().record_audit(
                action="tenant_isolation_blocked",
                actor=principal.user_id,
                job_id=job_id,
                detail=(
                    f"tenant {principal.tenant_id} attempted to read job "
                    f"{job_id} owned by tenant {owner}"
                ),
                attempted_tenant=owner,
            )
        except Exception:  # noqa: BLE001 — audit must not break the refusal
            logger.warning("cross-tenant audit write failed for job %s", job_id)
        return False

    async def _send_error(
        self, send: Send, scope: Scope, status: int, code: str, detail: str,
    ) -> None:
        # §8.1 stable envelope, mirroring PayloadLimitMiddleware._send_413;
        # the request_id comes from the outermost RequestIDMiddleware state.
        state = scope.get("state") or {}
        request_id = state.get("request_id") or request_id_var.get() or None
        body = api_error_response(status, code, detail, request_id)
        payload = json.dumps(body).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": payload})


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
