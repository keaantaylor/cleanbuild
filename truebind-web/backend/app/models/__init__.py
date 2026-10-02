"""Import every model module so Base.metadata is fully populated before
Alembic (or create_all in tests) inspects it."""

from . import alerts, audit, billing, blobs, channels, deliveries, exception_summary, identity, idempotency, jobs, leakage, leads, modules, obligations, reports, templates  # noqa: F401
