"""Worker-side job control — cancellation checkpoints, lease semantics, error taxonomy.

工业化指南 §14 任务 8 (docs/工业化商业化终极开发指南.md): the verify worker
cooperates with the API's MySQL-status cancellation CAS (POST /jobs/{id}/cancel
writes CANCELLED through MySQLStore.transition_job_status) at stage boundaries:

- checkpoints BEFORE and AFTER each Maven/differential execution and BEFORE
  each LLM retry iteration (check_cancelled / run_with_cancel_checks);
- on cancel the worker marks the job CANCELLED with reason
  'cancelled_at_checkpoint' and performs no further side effects;
- lease loss fails fast with reason 'lease_lost' (the worker stops writing
  business results the moment RedisStore.renew_lease stops returning True);
- classify_job_error maps every terminal exception onto the unified
  {class: system|repo|provider|policy|unknown, code, retryable, note}
  envelope written into the terminal reason (last_error) and progress events.

Layering: nodes call the checkpoint helpers at every execution boundary; the
worker (agent/worker.py) checks the same status at graph-stage boundaries and
owns the terminal writes. Without a job_id (CLI / eval runs) every helper is
a no-op, so non-worker invocations behave exactly as before.
"""
from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from httpx import ConnectError as HTTPConnectError
from httpx import HTTPStatusError
from httpx import TimeoutException as HTTPTimeout
from pymysql.err import InterfaceError as MySQLLinkError
from pymysql.err import OperationalError as MySQLOperationalError
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from storage.mysql import InvalidStateTransition, MySQLStore

# Stable reason strings written into terminal job state (last_error) and
# progress events — API tests and dashboards match on them, so they are
# part of the contract.
CANCELLED_AT_CHECKPOINT = "cancelled_at_checkpoint"
LEASE_LOST = "lease_lost"


class JobCancelledError(Exception):
    """The job's MySQL status is CANCELLED at a checkpoint — stop everything."""

    def __init__(self, job_id: str, stage: str) -> None:
        self.job_id = job_id
        self.stage = stage
        super().__init__(f"Job {job_id} cancelled at checkpoint {stage!r}")


class LeaseLostError(Exception):
    """RedisStore.renew_lease returned False — another worker owns the lease."""

    def __init__(self, job_id: str, worker_id: str) -> None:
        self.job_id = job_id
        self.worker_id = worker_id
        super().__init__(f"Job {job_id}: worker {worker_id} lost its lease")


class BuildFailure(Exception):  # noqa: N818 — domain term, public API
    """A Maven build / test execution failed inside the pipeline."""


class ProviderAuthError(Exception):
    """The LLM provider rejected the request credentials."""


@dataclass(frozen=True)
class ErrorClassification:
    """Unified terminal-error taxonomy (system|repo|provider|policy|unknown)."""

    cls: str
    code: str
    retryable: bool
    note: str

    def as_dict(self) -> dict[str, Any]:
        """The envelope written into terminal reasons/events (key 'class')."""
        return {
            "class": self.cls,
            "code": self.code,
            "retryable": self.retryable,
            "note": self.note,
        }


def classify_job_error(exc: BaseException) -> ErrorClassification:
    """Classify a terminal job exception for the reason/events contract.

    Rules (ordered, first match wins):
    - BuildFailure / ProviderAuthError (this module): repo / provider.
    - control-flow and policy (JobCancelledError, LeaseLostError,
      InvalidStateTransition): policy.
    - infrastructure: subprocess.TimeoutExpired, TimeoutError,
      ConnectionError, OSError, MySQL/Redis link errors → system, retryable.
    - commands the pipeline runs against the repo (git/mvnw/javac non-zero
      exit) → repo, not retryable.
    - HTTP provider failures (httpx): auth 401/403 and 4xx → provider, not
      retryable; 429/5xx → provider, retryable; transport errors → system.
    - everything else → unknown, not retryable.
    """
    if isinstance(exc, BuildFailure):
        return ErrorClassification(
            "repo", "build_failure", False,
            "Maven build or test execution failed",
        )
    if isinstance(exc, ProviderAuthError):
        return ErrorClassification(
            "provider", "provider_auth", False,
            "LLM provider rejected the request credentials",
        )
    if isinstance(exc, JobCancelledError):
        return ErrorClassification(
            "policy", "cancelled_at_checkpoint", False,
            "job cancelled at a worker checkpoint",
        )
    if isinstance(exc, LeaseLostError):
        return ErrorClassification(
            "policy", "lease_lost", False,
            "worker lost the job lease",
        )
    if isinstance(exc, InvalidStateTransition):
        return ErrorClassification(
            "policy", "invalid_state_transition", False,
            "job state machine refused the transition",
        )
    if isinstance(exc, subprocess.TimeoutExpired):
        return ErrorClassification(
            "system", "subprocess_timeout", True,
            "external command exceeded its timeout",
        )
    if isinstance(exc, TimeoutError):
        return ErrorClassification("system", "timeout", True, "operation timed out")
    if isinstance(exc, (RedisConnectionError, RedisTimeoutError)):
        return ErrorClassification(
            "system", "redis_unavailable", True, "Redis link failure",
        )
    if isinstance(exc, (MySQLOperationalError, MySQLLinkError)):
        return ErrorClassification(
            "system", "mysql_unavailable", True, "MySQL link failure",
        )
    if isinstance(exc, subprocess.CalledProcessError):
        return ErrorClassification(
            "repo", "command_failed", False,
            "repo command exited non-zero",
        )
    if isinstance(exc, HTTPStatusError):
        status = exc.response.status_code
        if status in (401, 403):
            return ErrorClassification(
                "provider", "provider_auth", False, "HTTP auth rejected",
            )
        if status == 429:
            return ErrorClassification(
                "provider", "provider_rate_limited", True, "rate limited",
            )
        if status >= 500:
            return ErrorClassification(
                "provider", "provider_server_error", True, "provider 5xx",
            )
        return ErrorClassification(
            "provider", "provider_http_error", False, "provider 4xx",
        )
    if isinstance(exc, HTTPTimeout):
        return ErrorClassification(
            "system", "http_timeout", True, "HTTP request timed out",
        )
    if isinstance(exc, HTTPConnectError):
        return ErrorClassification(
            "system", "http_connect", True, "HTTP connect failure",
        )
    if isinstance(exc, ConnectionError):
        return ErrorClassification(
            "system", "connection", True, "connection failed",
        )
    if isinstance(exc, OSError):
        return ErrorClassification(
            "system", "os_error", True, "OS-level I/O failure",
        )
    return ErrorClassification(
        "unknown", "unclassified", False,
        f"unhandled {type(exc).__name__}",
    )


def is_cancelled(job_id: str | None, store: MySQLStore | None = None) -> bool:
    """True when the job's MySQL status is CANCELLED (the API's cancel CAS).

    Best-effort by design: a MySQL read failure reports False — cancellation
    is a cooperative boundary, and infrastructure failures surface honestly
    at the terminal transitions instead of silently killing a healthy
    pipeline mid-run.
    """
    if not job_id:
        return False
    if store is None:
        store = MySQLStore()
    try:
        row = store.get_job(job_id)
    except Exception:  # noqa: BLE001 — best-effort checkpoint read
        return False
    return bool(row is not None and str(row.get("status", "")) == "CANCELLED")


def check_cancelled(
    job_id: str | None, stage: str, store: MySQLStore | None = None,
) -> None:
    """Checkpoint: raise JobCancelledError when the job was cancelled.

    Called BEFORE and AFTER each Maven/differential execution and BEFORE
    each LLM retry iteration. When the after-check raises, the caller never
    receives the execution result, so no business results get written.
    """
    if not job_id:
        return
    if is_cancelled(job_id, store):
        raise JobCancelledError(job_id, stage)


def run_with_cancel_checks[T](
    job_id: str | None,
    stage: str,
    executor: Callable[..., T],
    *args: Any,
    store: MySQLStore | None = None,
    **kwargs: Any,
) -> T:
    """Cancel checkpoints around one Maven/differential execution.

    The before-check refuses to start the execution on a cancelled job; the
    after-check refuses to RETURN the result (callers must not write
    business results) when the job was cancelled mid-execution.
    """
    check_cancelled(job_id, stage + "_before", store)
    result = executor(*args, **kwargs)
    check_cancelled(job_id, stage + "_after", store)
    return result
