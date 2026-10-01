"""Cross-platform file locking for the append-only revocation log (#138).

The lock is a sibling ``.lock`` file created with ``O_CREAT | O_EXCL``: the
create either wins or loses atomically on POSIX and on Windows, so two
processes appending to the same log can never interleave a line. A lock left
behind by a crash times out loudly instead of blocking the next writer
forever, and the stale file is unlinked by whoever finally acquires it.
"""

from __future__ import annotations

import os
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path


@contextmanager
def file_lock(lock_path: Path, timeout: float = 10.0) -> Generator[None, None, None]:
    """Acquire an exclusive lock on ``lock_path`` via a ``.lock`` sibling.

    Args:
        lock_path: The file being protected (the lock is its ``.lock`` sibling)
        timeout: Maximum seconds to wait before giving up

    Yields:
        None once the lock is held

    Raises:
        TimeoutError: If the lock cannot be acquired within ``timeout`` —
            the caller must treat that as "another process is active", never
            as "the other process finished".
    """
    lock_file = lock_path.with_suffix(lock_path.suffix + ".lock")
    start = time.monotonic()
    fd: int | None = None
    while True:
        try:
            fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            if time.monotonic() - start > timeout:
                raise TimeoutError(
                    f"Could not acquire lock on {lock_file} within {timeout}s"
                ) from None
            time.sleep(0.01)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        with suppress(OSError):
            lock_file.unlink(missing_ok=True)
