# TrueBind — Experiments, 12-Month Roadmap, 3-Year Roadmap

Compiled 2026-09-24. Every item traces to a finding in
`TRUEBIND_PRODUCT_REVALIDATION.md` (§ numbers) or a source in
`TRUEBIND_SOURCE_REGISTER.md` (`[Xn.n]`). Defect IDs P*, F*, S* and
benchmark IDs refer to REVALIDATION §3–§5 and §19.

**Governing constraint.** TrueBind currently has **no customer evidence**
(no pilot, no interview transcripts, no real bordereau from a paying or
prospective customer in the repo). The engine also has **verified
correctness defects against the Lloyd's v5.2 standard it claims to
implement**. So Stage 0 is: stop claiming, fix what is provably wrong,
and go and get real files. Strategy beyond that is conditional on
experiment outcomes.

---

## 1. Experiments (run before major strategic commitments)

Each experiment has a decision attached. "Sample" is the minimum needed to
make the decision, not a statistical-power claim. With samples this small,
results are **directional**. Report them as counts ("7 of 10"), never as
percentages dressed up as precision.

| ID | Hypothesis | Test | Sample | Metric | Pass | Fail | Decision |
|---|---|---|---|---|---|---|---|
| **X-0** | TrueBind's arithmetic is correct against v5.2 | Build a v5.2-conformant claims fixture from the guide's CR0126/CR0128/CR0130/CR0134/CR0155 definitions [B1.1]; include fees and previously-paid amounts | 1 fixture, ≥200 rows, hand-computed expected values | False mismatch count | 0 false mismatches, 0 missed planted mismatches | Any false mismatch | Blocks all customer demos until it passes (REVALIDATION §3.2) |
| **X-1** | DA teams spend material time on bordereaux ingestion and checking, and would pay to cut it | Structured interviews (script in §4) with MA DA/claims-ops staff, coverholder/TPA ops staff, and DA auditors | 12–15 interviews across ≥6 organisations | Hours/month per coverholder file; current tool; top 3 pains; who signs off | ≥8 of 12 report ≥1 FTE-day/month on checking *and* name a budget owner | <5 of 12, or no budget owner | Pass: proceed to X-2. Fail: re-scope (sender side, audit packs, or stop) |
| **X-2** | TrueBind handles **real** bordereaux | Obtain real (anonymised) claims bordereaux under NDA and run them through TrueBind | ≥50 files from ≥5 senders | % files ingested with 0 silent loss (row-count ledger vs manual count); mapping precision/recall vs the human-confirmed mapping; exceptions judged true/false by the customer | 0 silent-loss files; mapping precision ≥0.95 on confirmed fields; exception precision ≥0.8 | Any silent-loss file, or exception precision <0.6 | Fail: fix the engine before any commercial step |
| **X-3** | Onboarding a new sender format is fast | Time a DA analyst mapping a new coverholder file in TrueBind vs their current method | 10 new formats, 3 analysts | Minutes to confirmed mapping; corrections needed | Median ≤15 min and ≤⅓ of current method | ≥ current method | Pass: this is the wedge metric. Fail: onboarding is not the differentiator |
| **X-4** | Saved mappings reduce repeat effort ("map once") | Re-run month-2 and month-3 files from the X-2 senders with saved mappings | 5 senders × 3 periods | % fields auto-bound correctly on repeat; analyst minutes on repeat | ≥90% correct auto-binding; ≤5 min per repeat file | <70% | Pass: build the mapping registry (Q2). Fail: formats drift too much; invest in the drift UI |
| **X-5** | Exceptions are true positives often enough to keep trust | Customer labels every flagged exception in X-2 | ≥500 flagged items | Precision per rule; false duplicates specifically | Duplicate precision ≥0.8; arithmetic precision ≥0.95 | Duplicate precision <0.5 (the F1 period problem predicts this) | Fail: re-model dedupe on (claim ref, period) before shipping |
| **X-6** | Human review time per file is acceptable | Instrument the review UI (time on screen per exception, accept/reject) | 20 files | Minutes per 1,000 rows reviewed | ≤10 min per 1,000 rows for a "normal" file | >30 | Redesign triage (grouping, bulk actions) |
| **X-7** | AI cost is negligible relative to value | Log tokens per call (the `usage` fields) during X-2 | All X-2 calls | $/file | ≤$0.05/file | >$0.50/file | Revisit model choice or caching |
| **X-8** | Willingness to pay | Price-sensitivity questions plus a paid pilot offer after X-2 | Same organisations as X-1 | Paid pilots signed; price accepted | ≥2 paid pilots at ≥£10k | 0 paid pilots | Fail: managed-service or pivot decision (§3 Year-1 gate) |
| **X-9** | TrueBind's differentiation survives contact with incumbents | Hands-on trial of Charles Taylor Bordereaux Sync and one of VIPR/Vellum/Verodat (demo or trial on the same anonymised files) | 2 competitors, same 10 files | Silent-loss rows; not-evaluable handling; exception precision; onboarding minutes | TrueBind wins on ≥2 of 4 | Loses on all | Fail: do not position on "assurance"; consider integration or partnership instead |
| **X-10** | The evidence pack is useful to oversight/audit | Show the reconciliation + excluded-rows + mapping-provenance pack to 5 DA auditors / compliance staff | 5 people | "Would you accept this as evidence?" plus what's missing | ≥3 of 5 say usable with minor changes | ≤1 | Pass: E5 becomes the lead module |
| **X-11** | Sender-side readiness checking has pull | Offer a free "pre-submission check" to 10 coverholders/TPAs | 10 | Activation; repeat use next period | ≥4 repeat | ≤1 | Pass: PLG channel exists |
| **X-12** | The audit/accounting adjacency is real | 3 exploratory interviews with audit practitioners about PBC schedule intake | 3 | Pain intensity | Clear repeated pain *and* budget | Otherwise | Adjacency stays parked unless it passes |
| **X-13** | Hosted performance matches local | Deploy to the intended host; run the §5 benchmark harness remotely | 1k–100k rows | Same stage timings; poll error count | Within 1.5× local; 0 poll errors | >2× or any 5xx | Tune infrastructure or architecture |

---

## 2. 12-month roadmap

Stages are gated: a stage's commercial work only starts once the previous
stage's gate passes. The engineering items listed are the ones the
evidence requires, not a wish list.

### 0–30 days: "Stop the bleeding, get real files"

| Stream | Work | Evidence it responds to |
|---|---|---|
| Engineering: correctness | (1) Fix the incurred arithmetic to the v5.2 decomposition (CR0126 + CR0128 + CR0130, plus fees where mapped), with explicit NOT_EVALUABLE when a component is unmapped. Add CR0128/CR0134 and fee fields to `schema.py`. (2) Remove "paid to date"/"paid ytd" aliases from CR0126 (this-month) or add a separate cumulative field. (3) Fix the date-column re-parse that flips dd/mm → mm/dd when one value is ISO (P5); make date order an explicit, confirmed per-column choice. (4) Refuse to truncate: replace the 500-blank-row early stop with a bounded scan that *reports* and does not silently drop (P2). (5) Stop the claim-ref-only row being classed as a "title" (P1) and the narrow-sheet "Total" row being a claim (F2). (6) Flag two source columns bound to one field (P7). (7) **Never exclude a sheet as "summary" on the strength of partial alias matches.** A sheet with data rows and <N recognised fields must become "needs mapping", and the report must never show "score reliable" while any sheet is excluded without human confirmation (F3: 50% of claims dropped under a grade-5 report). | REVALIDATION §3.2, §4 |
| Engineering: reliability | (1) Move upload parsing off the event loop (`def` route or a thread pool) so one upload can't freeze the server (measured: `/health` blocked 18.7 s at 100k rows and 46.6 s at 250k). (2) Set SQLite WAL + `busy_timeout`, or require Postgres for anything beyond a demo (100k-row SQLite run: "database is locked" 500s on poll). (3) Paginate `/exceptions` and `/duplicates` and stop N+1 `db.get` per pair (250k rows: duplicates endpoint 38 s / 85 MB, over the frontend's 30 s timeout). (4) Upload size cap + decompressed-size cap + `defusedxml`. (5) Do not re-run AI mapping in the process job; persist the upload-time proposal. | REVALIDATION §5, §19 |
| Engineering: honesty | Make the test suite hermetic (tests currently write to the dev DB and rewrite tracked fixtures); fix the 2 fresh-checkout failures; fix 5 ESLint errors; resolve the `processing_phase` migration drift. Add a CI job that runs all of it on a clean container. | REVALIDATION §3.1 |
| Research | X-0; start X-1 recruiting (target DA ops leads via LMA/LIIBA events, LinkedIn, and InsTech); obtain NDA template | — |
| Product | Rewrite claims in the README and homepage: no "Lloyd's v5.2" claim until X-0 passes | REVALIDATION §3.2 |
| Design | None beyond error states for the new "cannot verify" outcomes | — |
| Security | File-upload hardening per OWASP [B4.1]; server-generated stored filenames; CSV-injection escaping on export [B4.4] | §19 |
| Customer validation | 5+ X-1 interviews booked | — |
| Commercial | None (nothing to sell yet) | — |

**Gate to 30–90:** X-0 passes; the 5 reliability items above are merged, with
the benchmark harness re-run showing 0 poll 5xx and `/health` < 1 s during
upload at 100k rows; ≥8 interviews done.

### 30–90 days: "Prove it on real data"

| Stream | Work |
|---|---|
| Engineering | Reporting-period model: add `(claim_ref, period)` identity so a claim repeated across monthly tabs is a *movement*, not a duplicate (F1); movement checks (paid-to-date must not decrease without explanation; closed claims reopening). Real worker process (RQ/Celery/Arq or a Postgres queue) with wall-clock and memory limits; the in-thread job cannot be killed or bounded today. Dedupe: replace 2-character prefix blocking with multi-key blocking plus caps (dedupe measured 144 s at 250k rows). Exact-duplicate pairs: emit clusters, not O(k²) pairs. |
| Research | X-2, X-3, X-5, X-9 (competitor trials), X-10 |
| Product | Mapping registry v0: save a confirmed mapping per sender, versioned, **suggested on re-upload, never auto-applied without a diff view** (see REVALIDATION §18 on feedback-loop risk) |
| Design | Review-queue redesign driven by X-6 timing: group exceptions by cause, bulk accept/reject with reason, and an "I could not check this" section visually distinct from "this is wrong" (already the design intent; keep it) |
| Security | Authentication (SSO/OIDC), org tenancy on every table, audit actor from identity not request body (S8), retention and deletion policy for uploads |
| Customer validation | ≥50 real files; labelled exceptions |
| Commercial | Draft pilot agreement; price hypotheses for X-8 (see `TRUEBIND_UNIT_ECONOMICS.md`) |

**Gate to 3–6 months:** X-2 pass (0 silent loss, exception precision ≥0.8);
X-3 shows onboarding ≤⅓ of the current method; ≥1 organisation willing to
start a paid pilot (X-8). **If X-2 or X-9 fails, stop feature work and
reconsider the category** (REVALIDATION §30 "what would change this
conclusion").

### 3–6 months: "First paid pilots"

| Stream | Work |
|---|---|
| Engineering | Premium bordereaux schema and rule pack (E2), including tax and FX fields from v5.2; FX handled as **data with provenance** (rate, date, source), never inferred |
| Product | Evidence pack v1 (E5): reconciliation, excluded rows, mapping provenance, rules applied, exceptions and their dispositions, as a signed PDF plus a JSON bundle. Port the governance-pack code from branch `claude/great-gauss-082g8l` only after reviewing it (not verified in this investigation) |
| Design | Sender-side "readiness check" flow (E4) if X-11 passes |
| Security | Pen test of the upload surface; SOC 2 readiness gap assessment (buyers will ask; don't claim it) |
| Customer validation | 2–3 paid pilots; weekly usage review |
| Commercial | Pilot pricing (see Unit Economics). Case study only with written permission |

### 6–12 months: "Repeatable"

| Stream | Work |
|---|---|
| Engineering | Monitoring across periods per sender (E11): drift in mapping, completeness trend, late or missing submissions (a period model is a prerequisite). Outbound connectors: S3/Azure Blob drop plus Snowflake/Postgres export (the Competitive Landscape shows VIPR Data Cloud on Snowflake; TrueBind should *feed* such warehouses, not replace them) |
| Product | API v1 for the check itself (upload → job → result + evidence) for BMS and TPA integration (E13), only if a pilot customer asks |
| Research | Re-run X-4/X-5 on 6 months of data; retention (logo and usage) |
| Security | SSO for all customers, per-tenant encryption keys if requested, DPIA |
| Commercial | Convert pilots to annual; 5–8 customers is the Year-1 target *if* gates pass (a target, not a forecast) |

---

## 3. Three-year strategic roadmap

### Year 1: reliability + product-market evidence (high confidence *that this is the right focus*; outcome uncertain)

- Correct against v5.2 (X-0), reliable at 250k rows, hermetic tests, auth
  and tenancy.
- Claims + premium assurance for a handful of Lloyd's / London-market DA
  teams, or coverholders if the sender-side hypothesis wins.
- **Year-1 gate:** ≥3 paying customers renewing *or* clear evidence of pull
  in one sub-segment. If not, the options are (a) become a managed-service
  business using the tool internally, (b) sell the engine or rule packs
  into an incumbent (partner or OEM), or (c) stop.

### Year 2: platform + integrations + expansion (conditional)

Conditional on the Year-1 gate:
- Rule packs as versioned data (per standard, per capacity provider, per
  binder), with binder-term validation (a capability incumbents document
  [B5.2, B5.7] and TrueBind lacks).
- Period-over-period monitoring (E11) as the recurring-revenue core.
- Integrations prioritised by pull: Snowflake/warehouse export → SharePoint/
  OneDrive and Outlook intake (where bordereaux actually arrive) →
  BMS connectors (VIPR, Tide) if partnership is possible.
- Assurance API for TPAs and BMS vendors (E13).

### Year 3: category expansion / infrastructure / enterprise (speculative)

Speculative and explicitly not planned:
- Becoming the independent "assurance layer" that capacity providers
  require coverholders to pass before submission: a network effect *if*
  multiple MAs adopt the same rule packs.
- Adjacent domain (accounting/audit PBC schedules) only if X-12 passes and
  the insurance business funds it.
- Enterprise features: data residency, private deployment.

### Separation of confidence

| Plan | Confidence | Why |
|---|---|---|
| Fix v5.2 arithmetic, reliability, security basics | **High** | Directly evidenced defects |
| Get 50 real files and 12 interviews before building more | **High** | No customer evidence exists |
| Assurance-layer positioning | **Medium–Low** | Consistent with regulation and HCI literature; untested with buyers; Bordereaux Sync occupies the slot |
| Premium, monitoring, evidence packs | **Conditional** | Depends on X-2/X-8/X-10 |
| API, network, adjacent industries | **Speculative** | No evidence yet |

---

## 4. Interview script for X-1 (keep it neutral; don't pitch)

1. Walk me through the last bordereau you received, from the email arriving to it being "done".
2. Where did it arrive, in what format, and how many different layouts do you receive per month?
3. What did you check, how, and how long did it take? What did you *not* check?
4. What happens when a number looks wrong? Who do you ask, and how long does the query take?
5. Tell me about the last time a data problem was found *late*. What did it cost?
6. What tool do you use today (VIPR, Tide, in-house, Excel)? What does it not do?
7. Who would have to sign off on buying something here? Is there a budget line?
8. If a tool said "I could not verify these 312 rows, here's why", would that help or annoy you?
9. What evidence do auditors, Lloyd's oversight or the FCA ask you for about this data?

Record answers verbatim. Do not summarise into "they loved it".

---

## 5. How subsequent Claude Code sessions should work on TrueBind

Derived from REVALIDATION §21 (agentic-SE evidence: A4.3–A4.7, B6.1):

1. **Start every session by running the hermetic test suite plus the benchmark
   harness** on a clean checkout, and record the actual numbers in the
   session's handoff. Never copy numbers forward from a previous handoff.
2. **Plan first** for any multi-file change (REVALIDATION §21). Write the plan
   into `AI/` *before* editing code.
3. **Behavioural verification is independent of the tests the change author
   wrote.** For every data-correctness change, add at least one
   *differential* check: a hand-computed fixture, or the v5.2 definition
   quoted in the test docstring. Passing tests showed 29.6% behaviour
   divergence in SWE-bench patches [A4.3]; this codebase's own history shows
   "passing" suites alongside the defects in REVALIDATION §3–4.
4. **Adversarial review in a fresh context** (a subagent or separate session)
   for every PR touching ingest, mapping, validation or persistence [B6.1].
5. **Keep `AI/HANDOFF.md` short and current.** Move history to
   `PROJECT_STATE.md`. The handoff was stale at the start of this
   investigation: it did not mention sessions 6–7, and PROJECT_STATE still
   warned that `main` had diverged after it had been merged.
6. **Never write "fixed", "robust" or "production-ready"** without the command,
   output and commit hash that shows it.
