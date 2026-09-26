"""Where the auth-mode default SQLite files live (identity, billing).

Both stores used to default to a bare relative path — ``sqlite:specproof_identity.db``
— so the file actually opened was resolved against the process working
directory. Starting the same deployment from another directory silently opened
an empty database: every user and token disappeared and the API answered 401
with no clue that the wrong file was in play. The CLI and the server run from
different directories then read (and write) two different "default" databases.

The default is therefore anchored here: ``SPECPROOF_DATA_DIR`` when set,
otherwise this repository's root. Explicit ``SPECPROOF_IDENTITY_URL`` /
``SPECPROOF_BILLING_URL`` values still win untouched — this module only decides
where a *default* file is placed, never which backend is used.
"""

from __future__ import annotations

import os
from pathlib import Path

#: This package's repository root (``api/data_paths.py`` -> parents[1]).
REPO_ROOT = Path(__file__).resolve().parents[1]

IDENTITY_DB_FILENAME = "specproof_identity.db"
BILLING_DB_FILENAME = "specproof_billing.db"


def data_dir() -> Path:
    """The directory the default SQLite files are placed in.

    ``SPECPROOF_DATA_DIR`` is created on demand so pointing it at a fresh
    directory is a working deployment choice rather than an
    "unable to open database file" boot failure.
    """
    raw = os.getenv("SPECPROOF_DATA_DIR", "").strip()
    if not raw:
        return REPO_ROOT
    path = Path(raw).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_sqlite_url(filename: str) -> str:
    """A cwd-independent ``sqlite:<absolute path>`` default for one file."""
    return f"sqlite:{(data_dir() / filename).as_posix()}"
