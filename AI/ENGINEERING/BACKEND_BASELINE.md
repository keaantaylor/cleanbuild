# Backend baseline (before the MVP hardening work)

Recorded 2026-09-24 on branch `claude/truebind-mvp-hardening`. The branch was
created from `309d8ca`, whose application code is identical to `main` at
`eee00cf`; the only difference is the added research docs. The full forensic
evidence is in `AI/RESEARCH/TRUEBIND_PRODUCT_REVALIDATION.md` (§1.4 tests,
§3–4 defects, §5 performance, §19 security). This file is the short
"before" record that later work is measured against.

## Test and quality gates (clean checkout; `backend/data/` deleted first)

| Gate | Command | Result |
|---|---|---|
| bordereaux pytest | `cd bordereaux && python -m pytest tests -q` | **35 passed, 8 errors**. The errors come from `test_boundary_fixture.py`, a script-style file that pytest collects. |
| bordereaux script suites | `python tests/test_{boundary_fixture,phase2..6,legacy_formats}.py` | all pass |
| backend pytest | `cd truebind-web/backend && python -m pytest tests -q` | **25 passed, 2 failed**. The 2 failures are in `test_exception_summary.py`, whose fixture uses the real developer DB. |
| backend pytest, after `alembic upgrade head` on the dev DB | same | 27 passed. The result depends on local state. |
| frontend typecheck | `npx tsc --noEmit` | clean |
| frontend lint | `npx eslint .` | **5 errors** (`react-hooks/set-state-in-effect`) |
| frontend build | `npm run build` | succeeds |
| migration drift | `alembic check` | **fails**. `reports.processing_phase` is in the migrations but not in the model. |
| test hygiene | running the suites | rewrites 10 tracked fixture files; writes to `backend/data/` |

## Known correctness defects (verified at baseline)

Defect IDs match the revalidation report §4. They are:

- the v5.2 incurred arithmetic (§3.2);
- F3, P2, P5, P5b, P6, F2, P17, P9, P1, F1, P7/P7b, P10, P11b, P13/P13b/P13c,
  P14, P18, P19, P3.

## Known security defects (verified at baseline)

- **S1** path traversal
- **S2** orphan report on a long filename
- **S3** no upload size limit
- **S4** decompression amplification
- **S6** CSV injection
- **S7** no auth or tenancy
- **S8** spoofable audit actor
- **S10** re-processing duplicates results
- no `defusedxml`

## Performance baseline (local; 4 vCPU; uvicorn with 1 worker; synthetic data)

| Rows (1 sheet, 10 cols) | DB | Upload (API blocked) | Processing | Dedupe | Persist | Peak RSS | Poll 5xx |
|---|---|---|---|---|---|---|---|
| 25k | SQLite | 4.7 s | 11.2 s | 1.93 s | 8.86 s | 413 MB | 0 |
| 100k | Postgres | 18.8 s | 68.8 s | 24.6 s | 43.0 s | 865 MB | 0 |
| 250k | SQLite | 46.9 s | 255 s | 144 s | 109 s | 1,734 MB | 5 |
| 250k | Postgres | 46.5 s | 261 s | 144 s | 115 s | 1,755 MB | 0 |

At 25k rows, upload time scales with the number of cells: 40 columns took
18.2 s and 100 columns took 47.6 s.

At 250k rows, the duplicates endpoint took 38–53 s and returned 85 MB.
