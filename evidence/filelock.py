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

#: The first poll waits this long; every further failure doubles it, up to
#: the cap.
#:
#: WHY A BACKOFF. A fixed 10ms spin asks the operating system the same
#: question a hundred times a second for as long as another process holds
#: the lock. The backoff asks it a handful of times, and the deadline is
#: unchanged: the lock is still given up at the same moment, and it is
#: still taken as soon as it is free -- only the number of wasted wake-ups
#: changes.
_LOCK_POLL_INITIAL = 0.01
_LOCK_POLL_MAX = 0.1


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
    delay = _LOCK_POLL_INITIAL
    while True:
        try:
            fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 0:
                raise TimeoutError(
                    f"Could not acquire lock on {lock_file} within {timeout}s"
                ) from None
            # never sleep past the deadline: the timeout is the promise
            time.sleep(min(delay, remaining))
            delay = min(delay * 2, _LOCK_POLL_MAX)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        with suppress(OSError):
            lock_file.unlink(missing_ok=True)
