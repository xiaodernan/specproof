#!/usr/bin/env python3
"""Generate an Ed25519 signing key for Merge Certificates (offline).

Why this script exists
----------------------
The product is fail-closed: without ``SPECPROOF_SIGNING_KEY`` (or
``SPECPROOF_SIGNING_KEY_FILE``) the certificate signer falls back to
unsigned digests and says so, never pretends to sign
(``evidence/signing.py``). When an operator DOES want real signatures,
the private seed has to be 32 random bytes — and the failure mode of a
weak or hand-made seed is unrecoverable: it signs certificates. A
copy-pasted "32 hex chars I typed" is not a secret, and this script is
the supported way to avoid that.

What this does
--------------
* With no argument: prints a fresh 64-char hex seed to stdout (and its
  public key to stderr, so piping stdout never leaks information).
* ``--output <path>``: writes the hex seed to *path* (0600 on POSIX) and
  prints nothing secret to stdout; the public key goes to stderr for
  pinning.
* ``--force`` is required to overwrite an existing *path*.

What it does NOT do
-------------------
It never reads stdin, never touches environment variables, never writes to
a repo path by accident (any *path* is the operator's choice), and never
makes the seed guessable. Distribution — getting this into a secret
store (KMS/HSM/vault) — remains the operator's decision; see
``docs/operations/RUNBOOK.md`` (the KMS-HSM欠账 is named there, and the
compose carrier is deliberately undelivered per the ledger's D08 ruling).

Exit codes: 0 — key generated (nothing secret printed); 1 — the output
file exists and ``--force`` was not given; 2 — usage error.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def public_key_hex(seed: bytes) -> str:
    """The Ed25519 public key of *seed*, raw bytes hex-encoded."""
    key = Ed25519PrivateKey.from_private_bytes(seed)
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return raw.hex()


def _write_secret_file(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(
            f"refusing to overwrite existing key file: {path}\n"
            "pass --force if you really mean to replace it — the old "
            "certificate stays verifiable under the old key, but nothing "
            "new can be signed with it anymore"
        )
    # 0600 on POSIX, best-effort on Windows (mode bits are advisory there).
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content.encode("utf-8"))
    finally:
        os.close(fd)
    if os.name == "posix":
        os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="write the hex seed to this file instead of printing it",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="allow overwriting an existing --output file",
    )
    args = parser.parse_args()

    seed = secrets.token_bytes(32)
    hex_seed = seed.hex()
    pub = public_key_hex(seed)

    if args.output is not None:
        _write_secret_file(args.output, hex_seed + "\n", args.force)
        print(f"wrote {args.output} (32-byte seed, hex, 0600 on POSIX)")
        print(f"public key (hex, pin it): {pub}", file=sys.stderr)
        return 0

    print(hex_seed)
    print(f"# public key (hex, pin it): {pub}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
