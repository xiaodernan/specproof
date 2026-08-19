"""Stable error codes and the §8.1 error envelope for the FastAPI surface.

Guide reference: docs/工业化商业化终极开发指南.md §8.1 — every error
response carries a stable machine-readable code plus schema_version;
clients must never depend on English exception strings or stack traces.

Wire shape of an error response (backward compatible with FastAPI clients
— the legacy detail key keeps its original value):

    {
        "detail": "<original detail, unchanged>",
        "error": {
            "code": "JOB_NOT_FOUND",
            "message": "<same text as detail when detail is a string>",
            "request_id": "3fa0c2e19b4d4a1f",
            "retryable": false
        },
        "schema_version": 1
    }

The route layer raises ApiError (an HTTPException subclass) with an
explicit code; plain HTTPExceptions raised elsewhere (auth, rate limiting,
framework validation) are mapped to a default code by status in
api/server.py. Bumping SCHEMA_VERSION or changing a code meaning is a
breaking change — update docs/openapi/baseline.json and the OpenAPI diff
gate in the same PR.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import HTTPException

SCHEMA_VERSION = 1

#: Stable error codes (§8.1 + extensions for paths the guide does not name).
AUTH_REQUIRED = "AUTH_REQUIRED"
TENANT_FORBIDDEN = "TENANT_FORBIDDEN"
QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
JOB_NOT_FOUND = "JOB_NOT_FOUND"
PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
EVIDENCE_UNVERIFIED = "EVIDENCE_UNVERIFIED"
RATE_LIMITED = "RATE_LIMITED"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
VALIDATION_FAILED = "VALIDATION_FAILED"
INTERNAL = "INTERNAL"
#: HTTP 409 state-machine conflict (cancel of a terminal job, concurrent
#: state change). Added on top of the guide named codes so the 409 path
#: carries a stable code instead of a semantic mismatch.
STATE_CONFLICT = "STATE_CONFLICT"
#: HTTP 404 for identity-admin resources (users/tokens). Cross-tenant job
#: reads keep JOB_NOT_FOUND — the two 404s must stay indistinguishable on
#: the wire (no existence leak), but admin endpoints may name the missing
#: resource for their own authenticated callers.
USER_NOT_FOUND = "USER_NOT_FOUND"

#: Stable code → canonical HTTP status.
ERROR_CODES: dict[str, int] = {
    AUTH_REQUIRED: 401,
    TENANT_FORBIDDEN: 403,
    QUOTA_EXCEEDED: 429,
    JOB_NOT_FOUND: 404,
    PROVIDER_UNAVAILABLE: 503,
    EVIDENCE_UNVERIFIED: 404,
    RATE_LIMITED: 429,
    PAYLOAD_TOO_LARGE: 413,
    VALIDATION_FAILED: 422,
    INTERNAL: 500,
    STATE_CONFLICT: 409,
    USER_NOT_FOUND: 404,
}

#: Default stable code per HTTP status for plain HTTPException instances
#: (explicit ApiError codes raised in the routes always take precedence).
DEFAULT_CODE_BY_STATUS: dict[int, str] = {
    400: VALIDATION_FAILED,
    401: AUTH_REQUIRED,
    403: TENANT_FORBIDDEN,
    404: JOB_NOT_FOUND,
    409: STATE_CONFLICT,
    413: PAYLOAD_TOO_LARGE,
    422: VALIDATION_FAILED,
    429: RATE_LIMITED,
    500: INTERNAL,
    503: PROVIDER_UNAVAILABLE,
}

#: Error code → failure class (§14.3). Clients derive retryable from the
#: class, never from the HTTP status or English text: client/permission/
#: not-found/conflict failures are permanent for the same request, while
#: degrade/execution-failure/rate-limit/internal failures may succeed on a
#: later attempt.
ERROR_CLASS_BY_CODE: dict[str, str] = {
    AUTH_REQUIRED: "client",
    TENANT_FORBIDDEN: "permission",
    QUOTA_EXCEEDED: "rate-limit",
    JOB_NOT_FOUND: "not-found",
    PROVIDER_UNAVAILABLE: "degrade",
    EVIDENCE_UNVERIFIED: "execution-failure",
    RATE_LIMITED: "rate-limit",
    PAYLOAD_TOO_LARGE: "client",
    VALIDATION_FAILED: "client",
    INTERNAL: "internal",
    STATE_CONFLICT: "conflict",
    USER_NOT_FOUND: "not-found",
}

#: §14.3 failure classes that may succeed on a later attempt.
RETRYABLE_CLASSES = frozenset({"degrade", "execution-failure", "rate-limit", "internal"})


def is_retryable(code: str) -> bool:
    """True when the code's failure class is retryable (§14.3).

    Unknown codes fail closed to False: a client must not retry a request
    whose failure class the server did not name.
    """
    return ERROR_CLASS_BY_CODE.get(code, "client") in RETRYABLE_CLASSES


def error_response(
    status: int, code: str, detail: object, request_id: str | None = None,
) -> dict[str, Any]:
    """Build the §8.1 error envelope body (without the legacy detail key).

    status is part of the public signature (every envelope is raised for
    exactly one HTTP status) and reserved for callers that log or relay the
    envelope; it is not duplicated inside the JSON because the transport
    already carries it. When request_id is omitted a fresh 16-hex id is
    generated so the field is never missing on the wire. retryable is
    derived from the code's failure class (§14.3): client/permission/
    not-found/conflict → False, degrade/execution-failure/rate-limit/
    internal → True.
    """
    rid = request_id if request_id is not None else uuid.uuid4().hex[:16]
    if isinstance(detail, str):
        message = detail
    else:
        message = json.dumps(detail, ensure_ascii=False, default=str)
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": rid,
            "retryable": is_retryable(code),
        },
        "schema_version": SCHEMA_VERSION,
    }


def api_error_response(
    status: int, code: str, detail: object, request_id: str | None = None,
) -> dict[str, Any]:
    """Full wire body: the legacy detail (unchanged) plus the envelope.

    Old FastAPI clients keep reading detail exactly as before (string for
    route errors, list for validation errors); new clients read
    error.code / error.message / error.retryable / schema_version instead
    of parsing English text.
    """
    return {"detail": detail, **error_response(status, code, detail, request_id)}


class ApiError(HTTPException):
    """HTTPException carrying a stable error code (§8.1).

    Drop-in replacement for HTTPException in routes: every existing
    "except HTTPException: raise" block still works, and the global handler
    in api/server.py renders the envelope while preserving the original
    detail value.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.error_code = code
