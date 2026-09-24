"""Domain value lists that vary by market/sender and must not be hardcoded
at their point of use. Override per deployment with environment variables
(comma-separated); values are compared case-insensitively."""

from __future__ import annotations

import os

_DEFAULT_CLAIM_STATUSES = "open,closed,reopened,void,cancelled,ntu,withdrawn,other"


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    raw = os.environ.get(name) or default
    return tuple(dict.fromkeys(v.strip().lower() for v in raw.split(",") if v.strip()))


# Claim statuses accepted without an `invalid_status` finding. "ntu" = not taken up.
CLAIM_STATUSES: tuple[str, ...] = _csv_env("TRUEBIND_CLAIM_STATUSES", _DEFAULT_CLAIM_STATUSES)
