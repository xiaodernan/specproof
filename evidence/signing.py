"""Ed25519 signing for Merge Certificates (P5 core).

Phase 0/1 used SHA-256 digests only — by policy a digest is NOT a
signature. P5 adds real cryptographic attestation: the certificate (or
rejection notice) is wrapped in an in-toto-style statement and signed
with Ed25519, binding issuer identity, requirement version, commit SHA
and evidence digests in one verifiable document.

Key management (fail-closed, never in source):
  SPECPROOF_SIGNING_KEY      hex-encoded 32-byte Ed25519 seed, or
  SPECPROOF_SIGNING_KEY_FILE path to a file containing the hex seed
When neither is set, signing is unavailable and the pipeline falls back
to unsigned digests (documented — never pretends to sign).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


class SigningError(Exception):
    """Raised when signing is impossible (missing/invalid key material)."""


def _seed_bytes() -> bytes:
    raw = os.getenv("SPECPROOF_SIGNING_KEY", "").strip()
    if not raw:
        key_file = os.getenv("SPECPROOF_SIGNING_KEY_FILE", "").strip()
        if key_file and Path(key_file).exists():
            raw = Path(key_file).read_text(encoding="utf-8").strip()
    if not raw:
        raise SigningError(
            "No signing key configured: set SPECPROOF_SIGNING_KEY or "
            "SPECPROOF_SIGNING_KEY_FILE (32-byte Ed25519 seed, hex). "
            "Falling back to unsigned digests."
        )
    try:
        seed = bytes.fromhex(raw)
    except ValueError as exc:
        raise SigningError("Signing key is not valid hex") from exc
    if len(seed) != 32:
        raise SigningError(
            f"Signing key must be 32 bytes, got {len(seed)}"
        )
    return seed


def load_private_key() -> Ed25519PrivateKey:
    """Load the signing key (or raise SigningError)."""
    return Ed25519PrivateKey.from_private_bytes(_seed_bytes())


def public_key_hex() -> str:
    raw = load_private_key().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return raw.hex()


def sign_statement(payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap a payload in an in-toto-style signed statement.

    Returns {"_type": "...", "subject": [...], "payload": ...,
             "signatures": [{"keyid", "sig"}]}. The payload is
    canonicalized (sorted keys) before hashing/signing so verification is
    deterministic.
    """
    key = load_private_key()
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    keyid = "sha256:" + hashlib.sha256(pub).hexdigest()[:32]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    signature = key.sign(canonical)
    return {
        "_type": "https://specproof.dev/attestation/v0.1",
        "subject": [
            {
                "name": "specproof-verification",
                "digest": {
                    "sha256": hashlib.sha256(canonical).hexdigest(),
                },
            }
        ],
        "payload": payload,
        "signatures": [
            {
                "keyid": keyid,
                "sig": base64.b64encode(signature).decode(),
            }
        ],
    }


def verify_statement(statement: dict[str, Any], public_key_hex_str: str) -> bool:
    """Verify a signed statement against an expected Ed25519 public key."""
    try:
        pub = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(public_key_hex_str)
        )
        canonical = json.dumps(
            statement["payload"], sort_keys=True, separators=(",", ":")
        ).encode()
        for sig_entry in statement.get("signatures", []):
            signature = base64.b64decode(sig_entry["sig"])
            pub.verify(signature, canonical)
            return True
    except Exception:
        return False
    return False


def sign_json_document(document: dict[str, Any]) -> dict[str, Any]:
    """Sign a certificate/rejection-notice document (simpler wrapper)."""
    return sign_statement(document)


def generate_key_hex() -> str:
    """Generate a fresh Ed25519 seed (for key provisioning)."""
    return Ed25519PrivateKey.generate().private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()
