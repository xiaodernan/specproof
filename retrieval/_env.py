"""The retrieval package's integer env reader.

``embeddings.py`` and ``rerank.py`` each carried a byte-identical copy of this
function (#492). Both read a numeric knob, clamp it to non-negative, and fall
back to the default when the value is absent or unparseable — a deliberately
forgiving policy, unlike ``storage/env_config.int_env`` which refuses a
non-numeric value by name.

That difference is a decision, not an accident:
``tests/unit/test_env_int_readers_policy_table.py`` pins every reader's policy
so changing one has to be deliberate.
"""
from __future__ import annotations

import os


def env_int(name: str, default: int) -> int:
    """A non-negative integer from env; absent or unparseable -> ``default``."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


__all__ = ["env_int"]
