"""Check modules (binder compliance, leakage, sanctions). See base.py."""

from __future__ import annotations

from collections.abc import Callable

from . import binder, leakage
from .base import CheckInput, ModuleResult

REGISTRY: dict[str, Callable[[CheckInput], ModuleResult]] = {
    "binder": binder.run,
    "leakage": leakage.run,
}

LABELS = {
    "binder": "Binder compliance",
    "leakage": "Leakage & overpayment",
    "sanctions": "Sanctions screening",
}
