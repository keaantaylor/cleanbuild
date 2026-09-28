# Data retention and deletion

**Rule (non-negotiable #7):** the application never modifies or deletes an uploaded original. Originals are stored write-once, content-addressed (`tenants/<tenant>/originals/<sha256>.<kind>`), with their SHA-256 recorded at upload and verified on every read.

## What "delete" means in TrueBind

| Action | Effect in the app | Original file | Derived rows | Audit |
|---|---|---|---|---|
| A user deletes a report (owner/admin) | Hidden everywhere: API 404, lists, overview, alerts, follow-ups, deliveries | kept, byte-for-byte | kept, hidden | `REPORT_DELETED` |
| The organisation's retention period ends | Same as above, done by the retention job | kept | kept, hidden | `REPORT_EXPIRED` |

Soft-deleted reports are filtered by one rule in `app/models/reports.py` (every ORM query; opt-in `include_deleted` for audit and operator tooling).

## Physical purge (operator, outside the application)

Purging is a storage-level decision taken by the data controller, not application code:

1. **Object storage lifecycle rule** on the originals bucket (S3/R2): expire objects under `tenants/*/originals/` after the agreed retention period (for Lloyd's claims records typically at least 6 years after claim closure — confirm with the customer's DPA). Enable bucket **versioning** and, where required, **Object Lock (compliance mode)** so even administrators cannot delete early.
2. **Database purge** of soft-deleted reports older than the retention period: an operator-run script (added in P10 with the backup/restore runbook), executed under change control, logged, and never exposed through the API.

The hash-chained audit log is kept for the life of the organisation's account; it holds no claim data beyond file names and hashes.
