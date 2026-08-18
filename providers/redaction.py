"""Secret redaction for model-bound text (P0-A3).

Repository contents (source, docs, diffs, tests) are untrusted data that
gets embedded in LLM prompts. If a repository contains historical secrets
(sk- keys, GitHub tokens, private keys, JDBC URLs with credentials), they
must never leave the host. Every prompt assembly point must run text
through redact_text() before transmission.

The redactor is deterministic and conservative: it replaces matches with
[REDACTED:<kind>] and returns (text, count) so callers can record how much
was scrubbed.
"""

from __future__ import annotations

import re

_PRIVATE_KEY = (
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    r".*?"
    r"-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
)

_PATTERNS: list[tuple[str, str, str]] = [
    (r"sk-[a-zA-Z0-9_-]{16,}", "llm_api_key", "CRITICAL"),
    (r"ghp_[a-zA-Z0-9]{36}", "github_token", "CRITICAL"),
    (r"github_pat_[a-zA-Z0-9_]{20,}", "github_pat", "CRITICAL"),
    (r"AKIA[0-9A-Z]{16}", "aws_access_key", "HIGH"),
    (_PRIVATE_KEY, "private_key_block", "CRITICAL"),
    (r"Bearer\s+[a-zA-Z0-9\-_.]{20,}", "bearer_token", "CRITICAL"),
    (r"jdbc:[a-z]+://[^\s]+@", "jdbc_credentials", "HIGH"),
    (r"(?:redis|amqp)://[^\s]+@", "url_credentials", "HIGH"),
    (
        r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}",
        "jwt",
        "MEDIUM",
    ),
]

_JOINED = re.compile(
    "|".join("(?P<" + name + ">" + pattern + ")" for pattern, name, _sev in _PATTERNS),
    re.DOTALL,
)


def redact_text(text: str) -> tuple[str, int]:
    """Replace secret-like spans. Returns (redacted_text, replacement_count)."""
    if not text:
        return text, 0
    counts: dict[str, int] = {}

    def _repl(match: re.Match[str]) -> str:
        kind = match.lastgroup or "secret"
        counts[kind] = counts.get(kind, 0) + 1
        return "[REDACTED:" + kind + "]"

    redacted = _JOINED.sub(_repl, text)
    return redacted, sum(counts.values())
