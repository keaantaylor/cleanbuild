# Competitive-advantage rebuild: Phase 3 (safe autonomy, audit, jobs), branch `rebuild`

| Area | Change |
|---|---|
| Execution policy | Every correction is classified by code: AUTO (value unchanged, e.g. text that is a number) applies at once; AUTO_WITH_POLICY (a rewrite such as Euro -> EUR) applies only when a person in the organisation approved the same rewrite before; REVIEW_REQUIRED; APPROVAL_REQUIRED for amounts, currency, status and dates (someone other than the proposer, unless they are the only writer, which is recorded); BLOCKED for formulas, header rows and the claim reference |
| Correction record | before, after, why, rule, evidence (rule version, expected, actual, message), proposer and time, policy and reason, approval (person or policy, second person, sole approver), re-check result. Migration 0022, additive |
| Versions | original, analysed (annotated workbook, hashed on first trail build), corrected, approved; SHA-256 on each; the source is never written. Fixed a bug where the corrected version's hash changed with the save time |
| Trail | `GET /reports/{id}/trail`: arrival (hash, channel, sender, who), every job, rules and ruleset, findings by rule, issues by status, corrections in full, versions, deliveries and webhooks, last re-check, unverified corrections, audit chain intact, stored source still matches its hash |
| Jobs | Re-checks of large workbooks (> 2000 rows, `RECHECK_INLINE_MAX_ROWS`) run as a RECHECK job (queued/running/retrying/succeeded/failed), retry-safe, leaving the report COMPLETE. Identical bytes from the same sender while one is queued or processing return the existing report instead of processing twice. Existing: Idempotency-Key replay, inbound email claimed once per message and attachment |

Checks: backend 403 passed (1 Windows-only memory-limit test); new tests for policy, approval, precedent, RECHECK job, trail, in-flight duplicates. Engine 100. Frontend lint, typecheck, 24 unit, build OK.
Existing and kept: the inbound email webhook is verified with a constant-time shared secret. Left: no screen yet for the trail or for policy badges on corrections.
