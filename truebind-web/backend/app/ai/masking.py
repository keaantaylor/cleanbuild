"""Masked samples: the shape of a value without its content.

Letters become X/x, digits become 9, punctuation and spacing are kept,
length is capped. "Harbour Freight Ltd" -> "Xxxxxxx Xxxxxxx Xxx",
"2024-03-15" -> "9999-99-99", "GBP 1,250.00" -> "XXX 9,999.99". Enough for a
model to tell a date from an amount from a reference; nothing a person can
be identified by."""

from __future__ import annotations

import math
from typing import Any

MAX_SAMPLE_CHARS = 24
MAX_SAMPLES = 3


def mask_value(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    out = []
    for ch in text[:MAX_SAMPLE_CHARS]:
        if ch.isdigit():
            out.append("9")
        elif ch.isalpha():
            out.append("X" if ch.isupper() else "x")
        else:
            out.append(ch)
    return "".join(out)


def masked_samples(values: list[Any], limit: int = MAX_SAMPLES) -> list[str]:
    seen: list[str] = []
    for v in values:
        m = mask_value(v)
        if m is not None and m not in seen:
            seen.append(m)
        if len(seen) >= limit:
            break
    return seen
