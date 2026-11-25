"""Single-use secret tokens (invitations, password resets)."""

from __future__ import annotations

import hashlib
import secrets


def new_token() -> tuple[str, str]:
    """
    Returns (raw_token, token_hash).

    The raw token (256 bits from the OS CSPRNG, URL-safe) is sent to the user once and
    never stored or logged. Only its SHA-256 hash is persisted. A fast hash is
    appropriate here (unlike passwords) because the input has full entropy and cannot
    be guessed or brute-forced offline.
    """
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
