"""Application-level encryption for secrets stored in the database (TOTP
seeds, SSO client secrets) and for short-lived signed tokens.

Keys are derived from SECRET_KEY with HKDF-SHA256, one key per *purpose*,
so a value encrypted for one purpose can never be decrypted as another.
Fernet = AES-128-CBC + HMAC-SHA256 with a timestamp (used for TTLs).

Outside production an unset SECRET_KEY falls back to a fixed development
key (logged once); production refuses to start without a real one
(app.settings).
"""

from __future__ import annotations

import base64
import logging
from functools import cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..settings import get_settings

logger = logging.getLogger("truebind.crypto")
_DEV_KEY = "truebind-development-only-key-never-use-in-production"


class DecryptionError(Exception):
    """The value was tampered with, expired, or encrypted for another purpose."""


@cache
def _fernet(purpose: str) -> Fernet:
    secret = get_settings().secret_key.get_secret_value()
    if not secret:
        logger.warning("SECRET_KEY is not set: using the development key (never acceptable in production)")
        secret = _DEV_KEY
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=f"truebind:{purpose}".encode()).derive(
        secret.encode()
    )
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(purpose: str, plaintext: str) -> str:
    return _fernet(purpose).encrypt(plaintext.encode()).decode()


def decrypt(purpose: str, token: str, ttl_s: int | None = None) -> str:
    try:
        return _fernet(purpose).decrypt(token.encode(), ttl=ttl_s).decode()
    except (InvalidToken, ValueError) as exc:
        raise DecryptionError(purpose) from exc
