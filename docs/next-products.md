# Next products (design only — nothing here is built)

_Written 2 October 2026 as Phase 7 of the strategy pass. Order of build is set by what the first pilots ask for;
see `docs/strategy.md` for the decision record._

All three reuse the same core: read any workbook layout (header detection, mapping with evidence, confirmation
by a person), run deterministic checks that cite a cell, and give the customer back **their own workbook**
annotated, plus a corrected copy and a query letter. The engine (`bordereaux/`) is already split so a new
product is mostly a new **schema** (fields + aliases) and a new **rule set** (rows in `bordereaux/rules.py`
style), not a new pipeline.

---

## 1. Premium and risk bordereaux

**Who:** the same coverholders/MGAs, who send premium and risk bordereaux monthly alongside claims. Same buyer,
same file habits, same managing agents returning files.

**Schema (Lloyd's CRS v5.2 premium/risk sections, starting subset):** certificate / risk reference, UMR /
binder reference, insured name and address, country and state of risk, risk inception and expiry, transaction
type (new, renewal, MTA, cancellation), gross premium, commission % and amount, taxes (IPT/levies by
jurisdiction), net premium due, currency, sum insured / limit, class of business, deductible.

**Checks (all cite a cell; outcome FAIL or REVIEW as today):**
| Check | Outcome |
|---|---|
| Net premium = gross − commission − taxes (within tolerance) | FAIL |
| Commission % × gross = commission amount | FAIL |
| Commission above the binder's agreed maximum | FAIL |
| Risk dates outside the binder period; expiry before inception | FAIL |
| Tax rate inconsistent with the country/state of risk (rate table, versioned) | REVIEW |
| Cancellation without a matching original risk in this or earlier files | REVIEW |
| Same certificate reported twice in a period (exact) / re-keyed (probable, corroborated) | FAIL / REVIEW |
| Country of risk outside the binder's territorial scope | FAIL |
| Sum insured above the binder line size | FAIL |
| Currency not permitted on the binder | FAIL |

**Reuse:** binder module (`app/checks/binder`) already holds period, limit, currencies; extend with commission
cap, territories and line size. Month-on-month becomes "premium movement": MTAs without an original, risks that
vanished without cancellation.

**Effort estimate:** schema + aliases 3–4 days; checks 5–7 days; tax-rate table and its maintenance is the
ongoing cost (decide: own the table, or ask the customer to upload theirs).

---

## 2. General spreadsheet health check (finance teams)

**Who:** finance teams outside insurance: month-end packs, supplier lists, expense exports. Not built until
the bordereaux product has paying customers (strategy.md).

**What changes:** no fixed schema. The customer (or a template) declares what each column is — a small type
system: identifier, name, date, amount, currency, category, percentage, free text — and which columns should
add up to which.

**Checks:** totals and subtotals that don't add up (row and column); duplicate identifiers; near-duplicate
names on different identifiers (same corroboration rule as claims: never name + date alone); dates as text,
impossible dates, future dates; amounts as text, mixed signs, mixed currencies in one column; values outside
the column's usual range (robust z-score, REVIEW only); broken formulas (`#REF!`, `#DIV/0!`) and hard-coded
numbers in a formula column; blank required cells.

**Outputs:** the same three — annotated workbook, corrected copy (formatting fixes only), query list.

**Risk:** "general" invites vague expectations. Launch with two named templates (supplier master file, expense
export) and a declared-columns mode, not "any spreadsheet".

---

## 3. AI-assisted mapping with Anthropic — off by default

**Goal:** fewer columns left for a person to map by hand on unusual layouts, without sending customer data.

**Design (extends `app/ai/` — the provider interface and masking already exist):**
- New provider `anthropic` behind the existing `AIProvider` interface (`structured(system, prompt, tool)`),
  model configurable (default: the current Claude Sonnet model), forced tool call returning
  `{source_column: field_code, confidence, reason}`.
- **What is sent:** only the column **headers** the alias rules could not place, plus up to three **masked
  value shapes** per column (`mask_value`: letters → X/x, digits → 9, capped at 24 characters), inside an
  `<untrusted_headers>` block the system prompt says never to obey. **No cell values, no sheet names, no file
  name, no customer name.** This is exactly what `test_ingest_sends_only_headers_and_masked_samples` already
  enforces for the current providers; the same test runs against the new one.
- **Off by default**, per organisation: a setting "AI-assisted mapping (Anthropic)" with a plain-English
  explanation of what is sent; the server-wide `AI_PROVIDER=anthropic` plus the organisation's opt-in are both
  required. Audit entry `AI_MAPPING_SUGGESTED` records model, headers sent and suggestions (already exists).
- Suggestions land as `MAPPED_BY_AI` in **review** and are never applied until a person confirms (existing
  rule); processing is refused until the sheet is confirmed.
- Data handling: Anthropic API with zero-data-retention where available on the account; region per Anthropic's
  current offering. The security page, privacy notice and DPA Annex 3 list Anthropic as a sub-processor
  **before** the first call is made.
- Cost/latency: one call per sheet with unmatched headers, within the existing per-report call cap
  (`AI_MAX_CALLS_PER_REPORT`) and time budget.

**Approval needed (not done):** sending data to a new external service (Anthropic) — even masked headers —
needs Kealan's sign-off, an Anthropic account with the right data terms, and the sub-processor change notice to
customers. Listed in PROGRESS.md under "Waiting for Kealan".

**Evaluation before launch:** run the 30 real-world header sets we have (stress files, REVIEWED_* files, pilot
files with consent) with AI off vs on; measure columns left unmapped and wrong suggestions; ship only if wrong
suggestions are < 2% and every one is caught at the confirmation step.
