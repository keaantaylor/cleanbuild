"""Import every model module so Base.metadata is fully populated before
Alembic (or create_all in tests) inspects it."""

from . import alerts, audit, exception_summary, leakage, obligations, reports, templates  # noqa: F401
