"""Identity store factory for the auth layer (SPECPROOF_IDENTITY_URL).

Mirrors the SPECPROOF_AGENT_JOBS_URL convention of storage/agent_jobs.py:
'' (in-memory), 'sqlite:<path>' or 'mysql://...'. The instance is cached
per URL so every request shares one store; changing the env var (tests,
restart) rebuilds it. When auth is enabled but no URL is configured the
default is a local SQLite file whose location is anchored by
api/data_paths.py (SPECPROOF_DATA_DIR, else the repo root) so dev
deployments survive restarts and every entry point opens one database
no matter which directory it was started from; tests always pass an
explicit sqlite: URL with a tmp_path database.
"""

from __future__ import annotations

import logging
import os

from api.data_paths import IDENTITY_DB_FILENAME, default_sqlite_url
from storage.identity import IdentityStore, build_identity_store

logger = logging.getLogger(__name__)

_cached_store: IdentityStore | None = None
_cached_url: str | None = None


def identity_url() -> str:
    """The configured URL, or the auth-mode default when enabled."""
    raw = os.getenv("SPECPROOF_IDENTITY_URL", "").strip()
    if raw:
        return raw
    from api.identity.config import auth_enabled

    return default_sqlite_url(IDENTITY_DB_FILENAME) if auth_enabled() else ""


def get_identity_store() -> IdentityStore:
    """The (cached) identity store for the current configuration."""
    global _cached_store, _cached_url
    url = identity_url()
    if _cached_store is None or _cached_url != url:
        _cached_store = build_identity_store(url)
        _cached_url = url
        logger.info("identity store ready: %s", url)
    return _cached_store


def reset_identity_store() -> None:
    """Drop the cached store (tests, reconfiguration)."""
    global _cached_store, _cached_url
    _cached_store = None
    _cached_url = None
