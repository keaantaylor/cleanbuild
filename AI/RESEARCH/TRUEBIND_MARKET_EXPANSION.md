# TrueBind — Market Expansion Hypotheses

Compiled 2026-09-24. Companion to `TRUEBIND_PRODUCT_REVALIDATION.md`. Source
IDs `[Xn.n]` refer to `TRUEBIND_SOURCE_REGISTER.md`.

**Read this first.** Almost everything in this file is a **hypothesis**. The
investigation found strong evidence for the *existence* of the core problem
(messy, late, unverifiable delegated-authority data) and **no first-hand
customer evidence** about which expansion a buyer would pay for. No customer
interview, pilot or willingness-to-pay test has been run. Scores below are
reasoned judgements, labelled as such, and exist to decide *which
experiments to run first*, not to justify building anything.

Scoring (1 = low, 5 = high). **Tech complexity** is scored *inversely to
cost*: 5 = cheap to build on what exists. **Evidence** is how much external
evidence supports the problem (not the solution).

---

## 1. What the current engine actually transfers

Before any expansion, it helps to be precise about what is reusable. From the
code (REVALIDATION §2):

| Engine component | Reusable as-is? | Notes |
|---|---|---|
| Multi-sheet reader, header detection, structural fallback | **Yes**, format-agnostic | Bounded at 50 header rows and 500 columns. Truncates silently after 500 blank rows (defect P2). |
| Row classification (blank / subtotal / repeated header / title) | **Yes** | Heuristic false positives and negatives verified (P1, P17, F2). |
| Alias + fuzzy + LLM column mapping with human confirmation | **Mechanism yes, content no** | Aliases and field list are hard-coded to 10 claims fields in `schema.py`. |
| Amount / date parsing with "unparseable ≠ zero" | **Yes** | Locale ambiguity defects (P5, P6). |
| Three-state arithmetic check | **Mechanism yes, formula no** | The formula is wrong vs v5.2 CR0155 (REVALIDATION §3.2). |
| Exact and fuzzy duplicate detection | **Partly** | No period/snapshot concept (F1); super-linear time (§5). |
| Reconciliation summary, excluded-row ledger, sheet audit | **Yes** | The strongest, most distinctive asset. |
| Persistence, API, UI | **No** for scale or multi-tenant use | No auth, no tenancy, event-loop blocking, unpaginated endpoints (§5, §19). |

**Implication.** The transferable asset is a *pattern*: read an untrusted
spreadsheet, bind it to a schema with provenance, refuse to guess, and account
for every row. It is not a finished data model. Every expansion needs a new
**domain schema and rule pack**. The engine becomes a platform only if the
schema, rules and aliases become *data* (versioned packs), not Python
constants.

---

## 2. Insurance expansion candidates

| # | Candidate | Customer | Problem | Evidence (problem) | Competition | Tech complexity (5 = cheap) | Distribution | Revenue potential | Defensibility | Overall |
|---|---|---|---|---|---|---|---|---|---|---|
| E1 | **Claims bordereaux assurance (fix the core first)** | Lloyd's MAs' DA/claims teams; London-market carriers | Unverifiable claims data; stale reporting | **4**: CUO quote [B2.2], v5.2 [B1.1], Solvency II Art 82 [B3.1] | Tide/Sync, VIPR, Vellum (HIGH) | 4 | 2 (no brand, no channel) | 3 | 2 | **Prerequisite.** Everything else depends on it being correct. |
| E2 | **Premium bordereaux assurance** | Same buyers plus credit control | Premium and tax reconciliation, late premium ("DA debt") | 3: v5.2 premium/tax fields [B1.1]; DA-debt articles are T4 | Same set | 3 (new schema, tax fields, FX) | Same channel as E1 | 4 (premium is where money moves) | 2 | **High priority after E1** |
| E3 | Risk bordereaux assurance | Underwriting, exposure management | Aggregation and exposure data quality | 3 | Same set plus exposure tools | 2 (wide schemas, geocoding) | Same | 3 | 2 | Medium |
| E4 | **Submission-readiness checking (sender side)** | Coverholders, MGAs, TPAs/DCAs *before* sending | Rejection, queries, oversight findings, coverholder removal | 3: coverholder removals [B2.3 headline]; lateness as review trigger (T4 only) | VIPR Portal, distriBind, Send | 4 (same engine, inverted UX) | **4**: many small senders; PLG possible | 2 per account; volume | 3 (network: rule packs per capacity provider) | **High, cheap to test** |
| E5 | **Audit / governance review packs** | DA oversight, internal audit, compliance | Evidencing oversight (Consumer Duty, Lloyd's DA standards) | 3: FCA outcomes monitoring [B3.2]; Solvency II DQ [B3.1] | Not explicit in competitor docs | 4 (reuse reconciliation + audit trail; port the old PDF pack) | 3 | 3 | **3–4** (evidence packs are sticky once auditors rely on them) | **High** |
| E6 | Payment leakage detection | Claims audit | Overpayment, duplicate payments | 2: plausible; no primary source retrieved | Claims-audit firms, analytics vendors | 2 (needs payment-level data) | 2 | 4 | 3 | Medium. The code exists on an old branch (not verified). |
| E7 | Claims reconciliation (bordereau vs ledger / TPA system) | Claims finance | Bordereau totals ≠ ledger / cash | 3 | Duco-type tools, BMSs | 3 | 3 | 4 | 3 | Medium–High |
| E8 | Loss-run standardisation | US commercial underwriters, brokers | PDF/Excel loss runs in 1,000 formats | 3 | **Cytora/Applied**, V7, document-AI vendors (HIGH) | 2 (PDF extraction) | 2 | 3 | 1 | **Low**: crowded, and it needs document AI TrueBind lacks |
| E9 | Property SOV cleaning | Property underwriters, brokers | Schedules of values with inconsistent addresses and COPE data | 3 | Exposure/geocoding vendors | 2 | 2 | 3 | 2 | Low–Medium |
| E10 | Reinsurance data preparation | Cedents, reinsurers | Treaty submissions, loss triangles | 2 | Supercede, Vellum | 2 | 2 | 3 | 2 | Low for now |
| E11 | **Partner data-quality monitoring ("map once, monitor forever")** | MAs overseeing many coverholders | Same coverholder, same mistakes, every month | 3: Deequ-style monitoring is proven in general [A2.3]; the DA lateness narrative [B5.9] | VIPR ("previously processed data") [B5.2], Vellum ("mix shifts") [B5.4] | 3 (needs stored mappings, period model, drift) | 3 | **4** (recurring) | **3–4** (history accumulates) | **High, after E1 plus a period model** |
| E12 | Automated partner onboarding | New coverholder / binder setup | Weeks to onboard a new format | 2: only competitor content [B5.10] | VIPR Intarga, Sunapto | 3 | 2 | 3 | 3 | Medium; test with X-3 |
| E13 | Assurance API / embedded assurance | BMS vendors, MGAs' systems, TPAs | Want checks inside their own pipeline | 2 | Scrub AI (API cleansing) [B5.8] | 3 | 3 (partner-led) | 3 | 2 | Medium; only after correctness is proven |
| E14 | Email / document ingestion | Everyone | Bordereaux arrive by email | 3 | Many | 2 | — | — | 1 | A feature, not a product |
| E15 | Portfolio intelligence | Underwriting leadership | Real-time performance | 3: CUO wants "ideally real time" data [B2.2] | VIPR Insights, Vellum (HIGH) | 2 | 2 | 4 | 1 | **Low**: a crowded destination, not a wedge |
| E16 | Near-real-time monitoring | Same | Same | 2 | Same | 1 | — | — | — | Only if partners send data more often; bordereaux are monthly |

**Recommended sequencing (judgement):**
E1 (fix correctness) → E5 (evidence packs) and E4 (sender-side readiness), both
cheap and both leveraging the refuse-to-guess ledger → E2 (premium) → E11
(monitoring, which needs the period model) → E7 or E13 depending on pull.
Explicitly **deprioritised**: E8, E9, E10, E15, E16. Strong incumbents own
them, or they need capabilities TrueBind doesn't have.

---

## 3. Adjacent industries (same pattern: many senders → canonical schema → validation → exceptions → approval → audit)

Scored on whether **TrueBind's architecture and its only real asset, the
refuse-to-guess, row-accounted ledger, transfers**. Market size was
deliberately *not* estimated: no primary market-size source was retrieved,
and inventing one would violate the brief.

| Industry / workflow | Pattern fit | Regulatory pull for evidence | Incumbents | Transfer of TrueBind asset | Verdict |
|---|---|---|---|---|---|
| Banking: counterparty / client data onboarding, regulatory reporting prep | High | High (e.g. BCBS 239 data-aggregation principles, not fetched this session) | Duco, internal data teams, large vendors | Medium: schemas and controls are bank-specific | Later, if ever |
| Accounting / audit: client PBC schedules, trial balances, sub-ledgers | High | High (audit evidence) | Audit tools, Excel, AI audit start-ups | **High**: "every row accounted for, nothing guessed" *is* an audit concept | **Most promising non-insurance adjacency** (hypothesis) |
| Asset management: fund admin / investor data, private-markets reporting | High | Medium–High | Specialist data vendors | Medium | Watch |
| Payroll: multi-country payroll inputs | High | Medium | Payroll platforms | Medium | Crowded |
| Healthcare admin: claims/eligibility files | High | High (but a heavy compliance burden: HIPAA etc.) | Clearinghouses | Low–Medium | Avoid for now (compliance cost) |
| Procurement / supplier data | Medium | Low | P2P suites, MDM | Low | Avoid |
| Logistics: carrier invoices, rate files | Medium | Low | Freight audit firms | Medium | Avoid (low evidence pull) |
| Property / construction: schedules, valuations | Medium | Low–Medium | Niche | Low | Avoid |
| Energy: meter/settlement files | Medium | Medium | Industry-specific systems | Low | Avoid |
| Government grants / returns | Medium | Medium | Many | Low | Avoid |
| Legal ops: e-billing (LEDES) | Medium | Low | e-billing platforms | Low | Avoid |

**Honest conclusion on adjacencies:** the *pattern* is universal (see the
general data-onboarding vendors OneSchema and Flatfile in the Competitive
Landscape §3). The *moat* is not: TrueBind's value is domain rules plus
evidence semantics. Moving industries means rebuilding the rule pack and
re-earning trust. **No adjacency should be pursued until the insurance
wedge has paying customers.** The accounting/audit adjacency is the one
worth an exploratory interview or two (roadmap X-12), because "evidence
that every row was accounted for" is native to how auditors work.

---

## 4. Category options (feeds REVALIDATION §12)

| Category | Fit to current code | Fit to evidence | Verdict |
|---|---|---|---|
| Bordereaux processor / BMS | Partial (claims only) | Crowded, post-DDM procurement underway | **No** |
| Data-quality engine (generic) | Engine yes, rules no | Crowded; no insurance edge | No |
| **Data-assurance layer for delegated-authority data** | Closest match to what is distinctive (ledger, not-evaluable, reconciliation) | Supported by regulation [B3.1, B3.2] and the automation-bias literature [A3] | **Yes, as the working hypothesis** |
| Delegated-authority platform | No | Incumbents | No |
| Insurance data OS | No | — | No (premature) |
| Financial reconciliation platform | Partial | Duco et al. | Only the claims-reconciliation module (E7) |
| AI data-ingestion platform | Partial | Commodity (importers) | No: AI mapping is table stakes |
| Assurance API | Future | Plausible; Scrub AI precedent | Later packaging of the same engine |
| Governance product | Partial (audit log, obligations) | Supported | As a **module** (E5), not a category |
| Managed service | Not built | Incumbents sell it (VIPR MS) | Possible **go-to-market wrapper** early on (people plus tool) to get real files; see Unit Economics |
