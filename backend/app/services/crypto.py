"""Symmetric encryption for per-user secrets (LLM API keys) at rest.

A Fernet key is derived from ``NERVETRACK_SECRET_KEY`` so operators can supply
any stable string rather than a base64 Fernet key. Keys are decrypted only
in-memory at call time and never logged.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import get_settings


def _fernet() -> Fernet:
    secret = get_settings().secret_key
    if not secret:
        raise RuntimeError("NERVETRACK_SECRET_KEY is not set")
    digest = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
