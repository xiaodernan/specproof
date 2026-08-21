"""§6.10 signature-checking stub — honest, fail-closed verification.

Protocol only: this module checks a manifest signature through an
INJECTED verifier (a marketplace runtime supplies its keyring-backed
verifier; evidence/signing.py's verify_statement is the repo's concrete
Ed25519 verification). The stub never fabricates a result:

- no signature block          -> UNSIGNED (the manifest claims nothing);
- no verifier configured      -> UNSIGNED (cannot check — honest);
- verifier lacks the key      -> UNSIGNED (KeyNotFoundError is an honest
  "cannot check": a missing key proves nothing, so it is never INVALID);
- verifier returns False      -> INVALID (checked, and it failed);
- verifier returns True       -> SIGNED.

The signed payload is canonical JSON (sorted keys, compact separators)
over the manifest's signed_fields (defaults live in plugins/manifest.py),
so any conforming verifier hashes exactly the bytes this module produces.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from plugins.manifest import DEFAULT_SIGNED_FIELDS, Manifest


class KeyNotFoundError(LookupError):
    """Raised by an injected verifier when the keyring lacks key_id."""

    def __init__(self, key_id: str) -> None:
        super().__init__(f"verification key {key_id!r} is not available")
        self.key_id = key_id


class SignatureVerifier(Protocol):
    """Injected verifier: True for a valid signature, False for a mismatch.

    Raise KeyNotFoundError when the key is not in the keyring.
    """

    def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool:
        """Check signature over payload for key_id."""
        ...


class SignatureStatus(StrEnum):
    """Outcome of a manifest signature check."""

    SIGNED = "signed"
    UNSIGNED = "unsigned"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class SignatureResult:
    """Verdict of check_manifest_signature (status plus audit detail)."""

    status: SignatureStatus
    key_id: str | None
    algorithm: str | None
    detail: str


def canonical_signed_payload(
    manifest: Manifest, signed_fields: Sequence[str] | None = None
) -> bytes:
    """Bytes a signer/verifier must hash: canonical JSON of the signed fields."""
    if signed_fields is None:
        if manifest.signature is not None:
            signed_fields = manifest.signature.signed_fields
        else:
            signed_fields = DEFAULT_SIGNED_FIELDS
    payload = {field: manifest.raw[field] for field in signed_fields}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def check_manifest_signature(
    manifest: Manifest, verifier: SignatureVerifier | None
) -> SignatureResult:
    """Verify the manifest signature with the injected verifier.

    Honest-status contract: a missing verifier or a missing key yields
    UNSIGNED ("cannot check"), never INVALID and never a silent SIGNED.
    """
    signature = manifest.signature
    if signature is None:
        return SignatureResult(
            SignatureStatus.UNSIGNED, None, None, "manifest carries no signature block"
        )
    if verifier is None:
        return SignatureResult(
            SignatureStatus.UNSIGNED,
            signature.key_id,
            signature.algorithm,
            "no verifier configured; signature not checked",
        )
    try:
        signature_bytes = base64.b64decode(signature.value, validate=True)
    except ValueError:
        return SignatureResult(
            SignatureStatus.INVALID,
            signature.key_id,
            signature.algorithm,
            "signature value is not valid base64",
        )
    payload = canonical_signed_payload(manifest)
    try:
        valid = verifier.verify(payload, signature_bytes, signature.key_id)
    except KeyNotFoundError as exc:
        return SignatureResult(
            SignatureStatus.UNSIGNED,
            signature.key_id,
            signature.algorithm,
            f"cannot verify: {exc}",
        )
    if valid:
        return SignatureResult(
            SignatureStatus.SIGNED, signature.key_id, signature.algorithm, "verified"
        )
    return SignatureResult(
        SignatureStatus.INVALID, signature.key_id, signature.algorithm, "mismatch"
    )
