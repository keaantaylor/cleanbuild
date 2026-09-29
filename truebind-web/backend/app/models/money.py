"""Money columns: exact decimals, never binary floats.

``Money`` stores NUMERIC(18,2) (exact on PostgreSQL, the production
database) and always hands back ``Decimal``. Every value is normalised once,
at the boundary, by ``to_money``: 2 decimal places, ROUND_HALF_UP; NaN,
infinity and non-numbers become NULL, never a number. The engine still
computes in float with a tolerance (ARCHITECTURE.md D1); this is where those
floats become money.

SQLite (development only) has no decimal type: values are quantised before
storage and converted back through ``str`` on read, so the Python side
still only ever sees 2-dp Decimals.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Numeric
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator, TypeEngine

CENT = Decimal("0.01")


def to_money(value: Any) -> Decimal | None:
    """Normalise anything numeric to a 2-dp Decimal; everything else is None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        value = repr(value)  # shortest round-trip text: 0.1 + 0.2 -> "0.30000000000000004"
    try:
        d = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    if not d.is_finite():
        return None
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


class Money(TypeDecorator[Decimal]):
    impl = Numeric(18, 2)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "sqlite":
            return dialect.type_descriptor(Numeric(18, 2, asdecimal=False))
        return dialect.type_descriptor(Numeric(18, 2, asdecimal=True))

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        money = to_money(value)
        if money is None:
            return None
        return float(money) if dialect.name == "sqlite" else money

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        return to_money(value)
