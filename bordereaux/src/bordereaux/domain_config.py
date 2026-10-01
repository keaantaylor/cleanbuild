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

# Words senders use for an accepted status, read as that status (compared
# case-insensitively, after trimming). "settled" is how many TPAs say "closed".
# Override with TRUEBIND_CLAIM_STATUS_SYNONYMS="settled=closed,re-opened=reopened".
_DEFAULT_CLAIM_STATUS_SYNONYMS = (
    "settled=closed,finalised=closed,finalized=closed,concluded=closed,"
    "re-opened=reopened,re opened=reopened,reopen=reopened,"
    "outstanding=open,live=open,active=open,new=open,notified=open,"
    "not taken up=ntu,declined=other,repudiated=other"
)


def _pairs_env(name: str, default: str) -> dict[str, str]:
    raw = os.environ.get(name) or default
    out: dict[str, str] = {}
    for item in raw.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            if k.strip() and v.strip():
                out[" ".join(k.strip().lower().split())] = v.strip().lower()
    return out


CLAIM_STATUS_SYNONYMS: dict[str, str] = _pairs_env("TRUEBIND_CLAIM_STATUS_SYNONYMS", _DEFAULT_CLAIM_STATUS_SYNONYMS)
