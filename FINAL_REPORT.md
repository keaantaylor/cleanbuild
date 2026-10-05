# Competitive-advantage rebuild: Phase 1 (make review usable), branch `rebuild`

| Change | Detail |
|---|---|
| Mapping | High-confidence matches sit behind one line ("N columns mapped automatically · M to decide"). Only uncertain or required-but-unmapped fields show; "Show all" and "Confirm all as proposed" kept |
| Root-cause grouping | One card per cause (rule + column): rows, amount affected per currency, severity, owner, fix. Downstream symptoms (e.g. a reconciliation failing because an amount is text) are linked to their cause on the same row and ranked after it |
| Bulk decision | `POST /reports/{id}/issues/bulk`: apply safe fix (only rules with a deterministic fix, via the existing corrections flow), send to sender, override (reason required), resolve. Server selects the rows from the cause key; lifecycle enforced per issue; one audit entry |
| Guided queue | The report opens on "Review issues": Issue n of N, the problem, exact Sheet!Cell, rule code + version, expected / actual / difference, all affected cells on demand, one action row; advances after each decision. Full report one tab away |
| Visuals | Light neutral surfaces, one blue primary; red "Requires reconciliation", yellow "Undetermined", green "verified", always as text; tabular right-aligned numbers, mono only for rule codes and cells |

Decisions on a generated 500-row file (510 rows, 82 findings): review 82 per-row findings -> 14 cause decisions; mapping 22 fields shown -> 0 to decide.

Checks: backend 393 passed, 36 skipped; new tests for symptom linking, bulk decisions, safe-fix limits, audit and isolation coverage. 1 failure is Windows-only (a child memory limit needs Linux). Locally on Windows the suite needs a shim, because storage chmods originals 0o400 and Windows then refuses to delete the staging file. CI/Linux is unaffected.
Frontend: lint, typecheck, 24 unit tests, production build OK. Not deployed; branch only.
