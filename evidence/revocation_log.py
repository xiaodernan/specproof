"""Certificate Revocation Log — append-only JSONL storage (#134).

The revocation log is an append-only file with one JSON object per line.
Each line is a signed revocation statement as produced by
CertificateRevocation.sign(). The file is opened in append mode with
a lock to ensure atomic writes across processes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from evidence.filelock import file_lock


class RevocationLog:
    """Append-only revocation log stored as JSONL (one signed revocation per line).

    Thread-safe and process-safe via fcntl flock. Each write is a single
    line, so readers can stream the file without parsing the whole thing.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def append(self, revocation: dict[str, Any]) -> None:
        """Append a signed revocation statement to the log.

        The revocation dict must already be a signed statement (as returned
        by CertificateRevocation.sign()).
        """
        line = json.dumps(revocation, separators=(",", ":"), sort_keys=True) + "\n"
        with file_lock(self.path), self.path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    def all(self) -> list[dict[str, Any]]:
        """Read all revocations from the log (newest first)."""
        revocations: list[dict[str, Any]] = []
        if not self.path.exists():
            return revocations
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    revocations.append(json.loads(line))
                except json.JSONDecodeError:
                    # Skip malformed lines — they're evidence of corruption
                    continue
        revocations.reverse()  # newest first
        return revocations

    def find_by_target(self, target_digest: str) -> list[dict[str, Any]]:
        """Return all revocations for a given target certificate digest."""
        return [
            r for r in self.all()
            if r.get("payload", {}).get("target") == target_digest
        ]

    def is_revoked(self, target_digest: str) -> bool:
        """Check if a certificate digest has been revoked."""
        return bool(self.find_by_target(target_digest))


def default_revocation_log() -> RevocationLog:
    """Build the default revocation log from environment.

    SPECPROOF_REVOCATION_LOG defaults to ./revocations.jsonl in the cwd.
    """
    path = Path(os.getenv("SPECPROOF_REVOCATION_LOG", "./revocations.jsonl"))
    return RevocationLog(path)


def append_revocation(revocation: dict[str, Any]) -> None:
    """Convenience: append a revocation to the default log."""
    default_revocation_log().append(revocation)


def list_revocations() -> list[dict[str, Any]]:
    """Read all revocations from the default log (newest first)."""
    return default_revocation_log().all()


def find_revocations(target_digest: str) -> list[dict[str, Any]]:
    """Find revocations for a target certificate in the default log."""
    return default_revocation_log().find_by_target(target_digest)


def is_revoked(target_digest: str) -> bool:
    """Check if a certificate digest is revoked in the default log."""
    return default_revocation_log().is_revoked(target_digest)
