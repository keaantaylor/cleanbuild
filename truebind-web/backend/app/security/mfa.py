"""TOTP second factor: setup, confirmation, verification, recovery codes and
the short-lived sign-in challenge.

- RFC 6238 TOTP (30 s steps, 6 digits, SHA-1 -- what authenticator apps
  support), accepting the previous/current/next step for clock drift and
  rejecting any step at or before the last one used (no replay).
- 10 recovery codes, shown once, stored as SHA-256; each works once.
- The challenge returned by /auth/login after a correct password is an
  encrypted, 5-minute token naming the user and tenant; it is useless
  without a valid code, and wrong codes count towards account lockout.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

import pyotp
from sqlalchemy.orm import Session

from ..models._util import utcnow
from ..models.identity import UserMfa
from ..settings import get_settings
from . import crypto

STEP_S = 30
CHALLENGE_TTL_S = 300
RECOVERY_CODES = 10
_PURPOSE_SEED = "totp"
_PURPOSE_CHALLENGE = "mfa-challenge"


@dataclass(frozen=True)
class Challenge:
    user_id: str
    tenant_id: str


def _hash_code(code: str) -> str:
    normalised = code.strip().lower().replace("-", "").replace(" ", "")
    return hashlib.sha256(normalised.encode()).hexdigest()


def get(db: Session, user_id: str) -> UserMfa | None:
    return db.get(UserMfa, user_id)


def is_enabled(db: Session, user_id: str) -> bool:
    row = get(db, user_id)
    return row is not None and row.confirmed_at is not None


def begin_setup(db: Session, user_id: str, email: str) -> tuple[str, str]:
    """(secret, otpauth URI). Replaces any unconfirmed seed; the caller must
    refuse when 2FA is already enabled."""
    secret = pyotp.random_base32()
    row = get(db, user_id)
    if row is None:
        row = UserMfa(user_id=user_id, secret_enc="", recovery_code_hashes=[], last_used_step=0)
        db.add(row)
    row.secret_enc = crypto.encrypt(_PURPOSE_SEED, secret)
    row.confirmed_at = None
    row.recovery_code_hashes = []
    row.last_used_step = 0
    uri = pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=get_settings().totp_issuer)
    return secret, uri


def verify_totp(row: UserMfa, code: str) -> bool:
    """Constant-time check of a 6-digit code against steps t-1..t+1 that are
    newer than the last accepted one. Records the step on success."""
    code = code.strip()
    if not (len(code) == 6 and code.isdigit()):
        return False
    secret = crypto.decrypt(_PURPOSE_SEED, row.secret_enc)
    totp = pyotp.TOTP(secret)
    now_step = int(time.time()) // STEP_S
    for step in (now_step - 1, now_step, now_step + 1):
        if step <= (row.last_used_step or 0):
            continue
        if hmac.compare_digest(totp.at(step * STEP_S), code):
            row.last_used_step = step
            return True
    return False


def confirm(row: UserMfa, code: str) -> list[str] | None:
    """Enable 2FA if the code is valid; returns the new recovery codes."""
    if not verify_totp(row, code):
        return None
    codes = [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}" for _ in range(RECOVERY_CODES)]
    row.recovery_code_hashes = [_hash_code(c) for c in codes]
    row.confirmed_at = utcnow()
    return codes


def consume_recovery_code(row: UserMfa, code: str) -> bool:
    h = _hash_code(code)
    hashes = list(row.recovery_code_hashes or [])
    match = next((x for x in hashes if hmac.compare_digest(x, h)), None)
    if match is None:
        return False
    hashes.remove(match)
    row.recovery_code_hashes = hashes  # reassign so the JSON column is marked dirty
    return True


def disable(db: Session, row: UserMfa) -> None:
    db.delete(row)


def issue_challenge(user_id: str, tenant_id: str) -> str:
    payload = json.dumps({"u": user_id, "t": tenant_id, "n": secrets.token_hex(8)})
    return crypto.encrypt(_PURPOSE_CHALLENGE, payload)


def read_challenge(token: str) -> Challenge | None:
    try:
        data = json.loads(crypto.decrypt(_PURPOSE_CHALLENGE, token, ttl_s=CHALLENGE_TTL_S))
    except (crypto.DecryptionError, ValueError):
        return None
    return Challenge(user_id=str(data["u"]), tenant_id=str(data["t"]))
