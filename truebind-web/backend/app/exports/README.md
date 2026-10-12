# Excel exports

Two downloads for a processed report:

| Endpoint | File | Built by |
|---|---|---|
| `GET /api/v1/reports/{id}/export/health-report.xlsx` | `TrueBind_Health_Report_<sender or file>_<YYYY-MM-DD>.xlsx` | `health_report.build_health_report` (XlsxWriter) |
| `GET /api/v1/reports/{id}/export/annotated.xlsx` | `<file>_REVIEWED.xlsx` | `app/services/deliverables.annotated_workbook` (openpyxl) |

Both routes are in `app/routes/deliverables.py`. Both need a reader in the report's organisation (404 otherwise)
and a `COMPLETE` report (409 otherwise). Every download is written to the audit trail as `EXPORT_GENERATED`
(who, when, which report, which file, size and SHA-256) and to the deliveries list. The annotated file returns
409 with a readable message when the stored original is gone (purged or failed its hash check). Originals are
always stored, so no migration is needed.

Both files are built in memory. The original is read with `store.read_bytes()`, and XlsxWriter runs with
`in_memory=True`, so no temporary file is written. The routes are sync, so FastAPI runs them in its threadpool
and they never block the event loop.

## Health Report structure

`data.collect(db, report, actor)` reads everything once into plain dataclasses (`HealthReportData`).
`build_health_report(data)` takes only those, so it can be tested and timed without a database
(`tests/perf_health_report.py`).

| Sheet | What it holds |
|---|---|
| Summary | Title block, the coverage banner (above every number), KPI tiles, Top 10 with links to Exceptions, two native charts and the tables they read |
| Coverage | Every sheet, every source column with its mapping state (all five), fields with no column, checks that couldn't run |
| Exceptions | One row per finding as an Excel Table: Severity is conditionally formatted; Status (dropdown) and Owner are editable |
| Duplicates | Duplicate pairs merged into groups, alternate group shading, Keep / Remove / Review suggestion |
| Reconciliation | Arithmetic findings: Expected, Reported, Difference as a live formula, per-currency `SUMIFS` totals |
| Missing Data | Field × sheet heat map (grey = couldn't map), then one row per missing value |
| Audit Trail | Upload, mapping confirmations, validation, this export, engine and ruleset versions, the hash-chained log |
| About This Report | How to read it, colour legend, the five mapping states, every check, disclaimer, truebind.ie |

House rules:

- **Coverage before results.** Never show a score or count without saying what was not read or checked. The
  wording is always "Couldn't check", as in the app.
- **A word next to every colour** (Error / Warning / Couldn't check), so the file reads in greyscale.
  "Couldn't check" cells also get a bold border.
- **Text is text.** `strings_to_formulas` and `strings_to_urls` are off, so customer values that start with
  `=` stay inert. The only formulas are ones written with `write_formula`.
- **One format per style.** Use the `Formats` cache in `theme.py` (`f.get(...)`, `f.text()`, `f.money(ccy)` and
  so on). Never call `workbook.add_format` per cell.
- **Money is never added across currencies.** Totals are per currency.

## Adding a sheet

1. Add the sheet name to `SHEETS` in `health_report.py`, in the order it should appear.
2. Write `def _my_sheet(ctx: _Ctx, ws) -> None`. Use `ctx.f` for formats, `ctx.issues` (already sorted) and
   `ctx.data`. Call `ctx.print_setup(ws, repeat_row=<header row>)`, freeze the header and add an autofilter.
   For long lists, write with typed calls (`write_string`/`write_number`) and skip empty cells.
3. Call it from `build_health_report`.
4. If it needs new data, add a field to `HealthReportData`, fill it in `data.collect`, and add it to
   `tests/perf_health_report.synthetic_data`.
5. Add assertions to `tests/test_health_report.py`. The tests re-open the file with openpyxl.

## Tests and timing

```
cd truebind-web/backend
.venv/Scripts/python -m pytest -q tests/test_health_report.py tests/test_deliverables.py
.venv/Scripts/python tests/perf_health_report.py 10000 10        # realistic: 0.5 findings per row
.venv/Scripts/python tests/perf_health_report.py 10000 10 1.2    # heavy: 1.2 findings per row
```

Build time scales with the number of findings, not rows. On the development machine (Python 3.14), a
10,000-row, 10-sheet file builds in about 2 s at 0.5 findings per row and about 5 s at 1.2.
