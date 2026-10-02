"""Organisation option: anonymise insured names.

When on, every insured name TrueBind stores about a file -- claim rows,
finding text, mapping samples and excluded-row values -- is replaced by a
stable code such as "Insured 7F3A21". The code is a keyed hash of the
normalised name, so the same insured gets the same code across files (month-on-
month and duplicates still line up) while the name itself is never stored.
Matching (duplicates) runs on the real names in memory before anything is
saved. The customer's own workbook, returned as the annotated copy, is theirs
and is not changed.
"""

from __future__ import annotations

import hashlib
import hmac
import re

from ..settings import get_settings


def _key(tenant_id: str) -> bytes:
    secret = get_settings().secret_key.get_secret_value() or "truebind-dev-secret"
    return hmac.new(secret.encode(), tenant_id.encode(), hashlib.sha256).digest()


def pseudonym(tenant_id: str, name: object) -> str | None:
    if name is None:
        return None
    norm = " ".join(str(name).split()).casefold()
    if not norm:
        return None
    return "Insured " + hmac.new(_key(tenant_id), norm.encode(), hashlib.sha256).hexdigest()[:6].upper()


class Replacer:
    """Replaces every known real name inside a piece of text (longest first)."""

    def __init__(self, tenant_id: str, names) -> None:
        mapping = {}
        for n in names:
            if n is None:
                continue
            s = str(n).strip()
            if len(s) >= 2 and s not in mapping:
                mapping[s] = pseudonym(tenant_id, s)
        self.mapping = mapping
        self._re = (re.compile("|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)))
                    if mapping else None)

    def __call__(self, text):
        if self._re is None or not isinstance(text, str):
            return text
        return self._re.sub(lambda m: self.mapping[m.group(0)], text)
