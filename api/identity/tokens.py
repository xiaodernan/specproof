"""Local scoped API tokens — sp_<id>_<secret> (MULTI_TENANT_DESIGN.md §1).

Storage stores two independent hashes and never the token itself:
  * token_hash = HMAC-SHA256(SPECPROOF_TOKEN_HMAC_KEY, full token) — used to
    find the row in constant time (an index lookup on a keyed hash);
  * secret_hash = bcrypt(secret) — checked with bcrypt.checkpw on use, so a
    leaked database cannot reconstruct usable secrets.

Tokens are show-once: mint_token() returns the cleartext exactly once; only
the hashes are persisted. Verification is fail-closed: an unconfigured HMAC
key, an expired token, a disabled user or any malformed input rejects.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time

import bcrypt

from api.identity.config import bcrypt_rounds, token_hmac_key
from api.identity.principal import Principal
from storage.identity import ApiTokenRow, IdentityStore, User

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "sp_"


class TokenConfigError(RuntimeError):
    """Minting requires SPECPROOF_TOKEN_HMAC_KEY (never a default)."""


def token_hash_for(token: str) -> str:
    """HMAC-SHA256 hex over the full sp_ token (keyed by the env key)."""
    key = token_hmac_key()
    if key is None:
        raise TokenConfigError(
            "SPECPROOF_TOKEN_HMAC_KEY is not configured; refusing to hash tokens"
        )
    return hmac.new(key.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_secret(secret: str) -> str:
    """bcrypt hash of the secret half (stored as an ASCII str)."""
    return bcrypt.hashpw(
        secret.encode("utf-8"), bcrypt.gensalt(rounds=bcrypt_rounds())
    ).decode("ascii")


def check_secret(secret: str, secret_hash: str) -> bool:
    try:
        return bcrypt.checkpw(secret.encode("utf-8"), secret_hash.encode("ascii"))
    except ValueError:
        return False


def mint_token(
    store: IdentityStore,
    user_id: str,
    name: str,
    scopes: str = "",
    ttl_days: int | None = None,
) -> tuple[ApiTokenRow, str]:
    """Create a scoped token row; returns (row, cleartext) — show once."""
    token_id = str(secrets.token_hex(16))
    # token_hex: the secret alphabet [0-9a-f] never contains '_', so the
    # sp_<id>_<secret> format stays unambiguous to parse.
    secret = secrets.token_hex(32)
    token = f"{TOKEN_PREFIX}{token_id}_{secret}"
    token_hash = token_hash_for(token)
    secret_hash = hash_secret(secret)
    expires_at: float | None = None
    if ttl_days is not None and ttl_days > 0:
        expires_at = time.time() + float(ttl_days) * 86400.0
    row = store.create_api_token(
        user_id=user_id,
        name=name,
        token_hash=token_hash,
        secret_hash=secret_hash,
        scopes=scopes,
        expires_at=expires_at,
        token_id=token_id,
    )
    return row, token


def _parse_token(raw: str) -> tuple[str, str] | None:
    if not raw.startswith(TOKEN_PREFIX):
        return None
    body = raw[len(TOKEN_PREFIX):]
    parts = body.split("_", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def principal_for_user(user: User, scopes: frozenset[str]) -> Principal:
    return Principal(
        user_id=user.id,
        tenant_id=user.tenant_id,
        roles=frozenset({user.role}),
        scopes=scopes,
    )


def verify_local_token(
    store: IdentityStore, raw: str, *, now: float | None = None
) -> Principal | None:
    """Exchange an sp_* bearer token for a principal, or None (reject).

    The full-token HMAC lookup, bcrypt secret check, expiry and user status
    all reject with None — callers map that to 401 without distinguishing
    why (no oracle for token probing).
    """
    parsed = _parse_token(raw)
    if parsed is None:
        return None
    token_id, secret = parsed
    try:
        token_hash = token_hash_for(raw)
        row = store.get_token_by_hash(token_hash)
    except Exception:  # noqa: BLE001 — fail closed on any store/HMAC failure
        logger.warning("token lookup failed; rejecting")
        return None
    if row is None or row.id != token_id:
        return None
    if not check_secret(secret, row.secret_hash):
        return None
    now_s = now if now is not None else time.time()
    if row.expires_at is not None and row.expires_at < now_s:
        return None
    user = store.get_user(row.user_id)
    if user is None or user.status != "active":
        return None
    store.touch_token_last_used(row.id, now_s)
    scopes = frozenset(s.strip() for s in row.scopes.split(",") if s.strip())
    return principal_for_user(user, scopes)
