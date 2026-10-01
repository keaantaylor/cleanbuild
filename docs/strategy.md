# TrueBind strategy (decision record)

_Recorded 1 October 2026. Owner: Kealan. Status: decided; revisit after the first 10 pilots._

## Decision: first market

TrueBind's first market is **small and mid-sized coverholders, MGAs and delegated claims administrators
(TPAs), UK and Ireland first**, who report claims bordereaux to Lloyd's syndicates and insurers and will not
buy an enterprise platform.

They feel the pain directly: when a bordereau is wrong, the managing agent or insurer sends it back, the
coverholder's team spends hours finding and fixing the errors, and the relationship suffers. They have no
budget or IT capacity for an integration project, and today they check files by eye in Excel.

## Who we are not selling to (yet)

- **Large managing agents and carriers.** They are served by established bordereaux platforms: VIPR,
  Charles Taylor (Bordereaux Sync, DDM / Tide), Verodat, Vellum and Brisc. These buyers run long procurement,
  want integrations and data pipelines, and are not where a small team wins first. They matter later as the
  *receivers* of the files our customers send, and as a channel ("ask your coverholders to check files with
  TrueBind first").
- **Banking: out of scope.** Reconciliation in banks is served by enterprise reconciliation vendors and is
  bought through long, security-heavy procurement. Nothing in our first product needs it.

## Possible second product (design only)

A general **spreadsheet health check for finance teams** (month-end packs, supplier lists, expense
exports): the same engine (read any layout, check structure, arithmetic, duplicates, formats; give back the
customer's own workbook with annotations). Not built until the bordereaux product has paying customers. See
`docs/next-products.md`.

## Differentiation

| What the customer gets | Why it matters to a small firm |
|---|---|
| **No integration**: upload the file as it is | No IT project, no data pipeline, results the same day |
| **Results in the customer's own workbook** (annotated copy) | Staff keep working in Excel; nothing new to learn |
| **A corrected copy plus a query letter** | Safe fixes done for them; the rest becomes a ready-to-send email to the sender |
| **Evidence**: what was checked, what wasn't, with cell references | They can show the managing agent exactly why the file is right |
| **Hosted in the EU** (once the database move is approved — see PROGRESS.md) | GDPR comfort for Irish and UK firms |
| **Priced for small firms**: per file or a low monthly fee, first file free | No enterprise contract |

## What success looks like in the first 6 months

- 10 pilots with coverholders/MGAs/TPAs; at least 5 convert to paid.
- Files returned by the managing agent fall by half for pilot customers.
- Each bordereau check takes under 5 minutes of the customer's time, including reading the report.
