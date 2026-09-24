# TrueBind — Business Model and Unit Economics (indicative)

Compiled 2026-09-24. **No prices here are TrueBind prices and none are
market facts** unless a source ID `[Xn.n]` is given. Where a number is an
assumption, it is labelled **ASSUMPTION** with the reasoning, so it can be
replaced by real data from experiments X-1 and X-8
(`TRUEBIND_STRATEGIC_ROADMAP.md`).

---

## 1. What was actually measured (cost side)

From the HTTP benchmark on this session's container (4 vCPU, 15 GB RAM,
local SQLite and local Postgres 16, **no network latency, no hosted
infrastructure**; see REVALIDATION §5):

| Measure | 25k rows, 1 sheet (SQLite) | 100k rows, 1 sheet (Postgres) | 250k rows, 1 sheet (SQLite) |
|---|---|---|---|
| Server CPU-seconds for the whole flow | see REVALIDATION §5 table | 121.1 s | 446.7 s |
| Peak server RSS | 413 MB | 865 MB | 1,734 MB |
| Postgres storage after processing | — | — | 163 MB total (claim_rows 89 MB, validation_results 66 MB), about 650 B per source row |
| LLM tokens | 0 (no API key; AI path not exercised) | 0 | 0 |

**LLM cost per call (estimated, not measured).** Prompt text built from the
actual code with a chars÷4 heuristic, since no API key was available to
call `count_tokens` or read `usage`:

| Call | Input tokens (est.) | Output tokens (ASSUMPTION) | Model in code | Price [B7.1] | Cost per call (est.) |
|---|---|---|---|---|---|
| Column-mapping fallback (per sheet with unmatched headers) | ~600 prompt+tool, plus ~300 tool-use system overhead ≈ 900 | 300 | Claude Haiku 4.5 | $1 in / $5 out per MTok | ≈ **$0.0024** |
| Exception triage narrative (per request) | ~2,000 + overhead ≈ 2,300 | 800 | Claude Haiku 4.5 | same | ≈ **$0.0063** |

Two code facts change these numbers:
- Mapping proposals are generated **twice** per report: once at upload and
  again inside the `/process` job (`routes/mapping.py` `_run_pipeline_job`
  calls `propose_mapping_for_workbook` again). That doubles AI calls per
  sheet with no benefit, and the second proposal can differ from the one
  the human confirmed.
- The narrative is regenerated on every click of "regenerate".

**Conclusion on variable cost:** for a 20-sheet file needing AI on every
sheet, AI costs ≈ 20 × 2 × $0.0024 ≈ **$0.10**. Compute is about
$0.01 (ASSUMPTION: $0.05 per vCPU-hour, typical of cloud on-demand
pricing; not sourced). Storage is about 650 B/row. **Variable cost per
file is cents. The economics are decided by people (onboarding,
review, support, sales), not by tokens or compute.** This agrees with the
general finding that the cost in this market is manual processing [B2.1:
one MA spent about 0.25% of GWP on data collection (interested-party
figure); B3.3: median 25% of actuarial time on data quality (2006, n=38)].

The **real infrastructure cost driver is memory**. A single 250k-row job
peaks at 1.7 GB in a single process that also serves HTTP. Safe hosting
needs a worker tier sized for the largest expected file (≥2–4 GB per
concurrent job) and a separate API tier. That is a fixed monthly cost, not
a per-file one.

---

## 2. Pricing evidence available

| Evidence | Value | Tier |
|---|---|---|
| Verodat bordereaux trial | **€15,000** for a 3-week trial, "fully redeemable if you continue"; "No per-binder fees" [B5.5] | T2 (vendor page, via search snippet) |
| VIPR, Tide, Vellum, distriBind, Send | **No public prices** | — |
| OneSchema (adjacent generic importer) | $0–$200/user/month studio tiers; credits at $0.012; importer tiers "custom" [B5.11] | T2 |
| Cost of the manual status quo | ~0.25% of GWP on data collection at one MA [B2.1] (vendor-CEO anecdote) | T4 |

That is thin. **Any price below is a hypothesis for X-8, not a
recommendation.**

---

## 3. Pricing-model options

| Model | Fits how DA work is organised? | Pros | Cons | Verdict |
|---|---|---|---|---|
| Per row | No: buyers don't think in rows | Tracks cost | Punishes large, clean files; unpredictable bills | Reject |
| Per file / workbook | Partly | Simple | Senders split or merge files; one file can hold 20 senders | Reject as the primary meter |
| **Per active sender (coverholder/TPA/binder) per month** | **Yes**: DA teams manage *relationships*, and onboarding cost is per sender | Predictable; aligns with the onboarding effort and the value of monitoring | Needs a definition of "active" | **Primary hypothesis** |
| Per seat | Weak | Familiar | Value isn't per user; discourages sharing with auditors | Secondary (reviewer seats free, admins paid) |
| Platform fee plus usage | Yes, for enterprise | Covers fixed hosting and support | Complex | For larger MAs |
| Implementation / onboarding fee | Yes | Pays for mapping the first N senders | Friction | Charge for >N senders or bespoke rule packs |
| Managed service (TrueBind staff run the checks) | Yes, *early* | Gets real files; revenue before the product is self-serve | Linear cost; competes with BPOs and VIPR Managed Services [B5.2] | **Useful as a Stage-1 wedge**, not as the end state |
| Premium modules (evidence packs, monitoring, premium bordereaux) | Yes | Expansion revenue | Needs a core that works first | Year 2 |
| API pricing (per check) | For BMS/TPA partners | Embeds TrueBind | Needs proven correctness | Year 2+ |
| White label | For BMS vendors | Distribution | Margin, dependency | Only if an incumbent asks |

---

## 4. Indicative unit economics (every input is an ASSUMPTION unless cited)

### 4.1 Scenario inputs

| Input | Low | Base | High | Basis |
|---|---|---|---|---|
| Active senders per customer | 10 | 30 | 80 | ASSUMPTION: a mid-size MA with a modest DA book, up to a large DA writer |
| Price per active sender per month | £40 | £100 | £200 | ASSUMPTION, anchored so the Base case (£36k/yr) lands near the only public data point (a €15k *trial* [B5.5]) |
| Files per sender per month | 2 | 3 | 5 | ASSUMPTION: monthly claims plus premium plus risk |
| Rows per file | 500 | 2,000 | 10,000 | ASSUMPTION |
| New-sender onboarding effort (TrueBind staff hours) | 0.5 | 2 | 6 | ASSUMPTION: 2–4 h per sender claimed by a mapping vendor [B5.10] (T4); X-3 must measure it |
| Blended staff cost per hour | £60 | £80 | £110 | ASSUMPTION: UK analyst/CS cost incl. overhead |
| Support + CS hours per customer per month | 4 | 8 | 20 | ASSUMPTION |
| Sales cycle / CAC per customer | £15k | £30k | £60k | ASSUMPTION: enterprise insurance sales, founder-led; no primary source |
| Gross logo churn per year | 5% | 15% | 30% | ASSUMPTION |

### 4.2 Base-case customer (30 senders, £100/sender/month)

| Line | Per month | Per year | Derivation |
|---|---|---|---|
| **Revenue** | £3,000 | £36,000 | 30 × £100 |
| LLM cost | ≈ £1 | ≈ £12 | 30 senders × 3 files × ~5 AI calls × ~$0.003, with double-call overhead included |
| Compute (variable) | ≈ £1 | ≈ £12 | 90 files × ~2k rows is well under 1 CPU-hour per month |
| Storage + DB | ≈ £2 | ≈ £24 | ~650 B/row × 180k rows/month ≈ 0.12 GB/month cumulative, plus backups (ASSUMPTION: managed PG storage at ~£0.1–0.2 per GB-month) |
| Network | ≈ £0 | ≈ £0 | Files are MBs |
| **Shared fixed hosting (allocated)** | £150 | £1,800 | ASSUMPTION: API plus worker (4 GB) plus managed Postgres plus object storage, about £600–£1,500/month for the platform, spread over 4–10 customers early on |
| Support + CS | £640 | £7,680 | 8 h × £80 |
| Onboarding (year 1) | — | £4,800 | 30 senders × 2 h × £80 |
| **Gross margin, year 1** | | **≈ £21.6k (60%)** | £36,000 − £14,328 |
| **Gross margin, year 2+** (no initial onboarding; ~20% sender churn re-onboarded) | | **≈ £25.5k (71%)** | |
| CAC | | £30k | ASSUMPTION |
| **CAC payback** | | **≈ 15–17 months** | £30k ÷ (£21.6k / 12) |

### 4.3 Sensitivity (what actually matters)

| Change | Effect on base gross margin | Interpretation |
|---|---|---|
| LLM cost ×10 (e.g. switching to Opus-class at $4/$20 [B7.1] with bigger prompts) | −£100/yr | **Irrelevant.** AI model choice is a quality decision, not a cost decision, at this volume. |
| Onboarding 6 h/sender instead of 2 | −£9.6k in year 1 (60% → 33%) | **The single biggest lever.** This is why X-3 (onboarding minutes) is the wedge metric. |
| Support 20 h/month instead of 8 | −£11.5k/yr | Second biggest. Reliability defects (REVALIDATION §5) become support hours. |
| Price £40 instead of £100 | Revenue £14.4k; year-1 gross margin ≈ **£0** (£14,400 − £14,328), before CAC | Low price is only viable with near-zero onboarding and support (self-serve). |
| 80 senders at £100 (same support hours) | Revenue £96k; year-1 margin ≈ 73% (onboarding £12.8k) | Larger DA books carry the economics. |

**Low case** (10 senders × £40, 6 h onboarding, 20 h/month support):
revenue £4.8k/yr against people costs over £20k/yr. **Deeply negative.**
Small customers only work self-serve.

**High case** (80 senders × £200, 0.5 h onboarding, 4 h/month support):
revenue £192k/yr; gross margin above 95%. It requires onboarding to be
nearly automatic, which is exactly the unproven claim.

---

## 5. AI economics and "map once, learn forever"

### 5.1 Where AI is economically justified

| Task | Deterministic | Cheap model (Haiku-class) | Expensive model | Human | Cached / learned |
|---|---|---|---|---|---|
| Reading cells, parsing numbers and dates, row counting, arithmetic, reconciliation, duplicate keys | **Always** | Never | Never | Confirms ambiguous locale choices | — |
| Header → field mapping for known aliases | **Yes** (alias table) | — | — | Confirms | Saved per sender |
| Header → field mapping for unseen or multilingual headers | Fallback structural | **Yes**, proposes with calibrated confidence | Only if cheap-model confidence is low *and* the sheet is large | **Must confirm** | Saved after confirmation |
| Scale/unit/basis interpretation ("(USD m)", "paid to date" vs "this month") | Parse tokens | Propose | — | **Must confirm, per column, shown in the UI** | Saved per sender, **re-confirmed if header text changes** |
| Sheet classification (claims vs summary vs notes) | Heuristic | Propose | — | Confirms when not "claims" | Saved |
| Exception explanation / triage narrative | Aggregation is deterministic | Summarise **only**, numbers verified post-hoc (already implemented) | — | Reads | — |
| Final truth (amounts, counts, currency, pass/fail) | **Only** | **Never** | **Never** | Signs off | — |

At measured volumes, AI cost is not the constraint (§4.3). The reason to
cache and learn is **consistency and reviewer time**, not token spend.

### 5.2 The feedback loop, designed with its risks

```
human confirms / corrects a mapping (with reason)
  → store as VERIFIED MAPPING {sender_id, sheet signature, header text hash,
    header→field, scale, basis, confirmed_by, confirmed_at, file_id}
  → next file from the same sender: exact signature match ⇒ PRE-FILL (not auto-apply),
    shown as "saved mapping from <date> by <person>"
  → drift detector: header text changed, column moved, value distribution changed
    (e.g. magnitudes ×1000, date order flipped) ⇒ demote to PROPOSED, require re-confirm
  → only pre-filled fields skip the AI call ⇒ fewer calls, faster onboarding
  → cross-sender alias learning: NOT automatic; a new alias enters the global
    table only through a reviewed change (a versioned rule-pack release)
```

| Risk | Mechanism | Mitigation |
|---|---|---|
| **Silent propagation of a wrong mapping** | Month-1 mistake auto-applied forever | Pre-fill, never auto-commit; show provenance; periodic re-attestation |
| **Automation bias** | Reviewers rubber-stamp pre-filled mappings [A3.3, A3.5] | Cognitive forcing on high-risk fields (amounts, scale, currency): the reviewer must actively choose [A3.13]; show confidence and sample values [A3.11] |
| **Poisoning / cross-tenant leakage** | One customer's odd alias pollutes another's suggestions (OWASP LLM04 [B4.2]) | No automatic cross-tenant learning; global aliases only via reviewed releases |
| **Semantic drift with the same header** | "Paid" switches from cumulative to this-month without a header change | Value-distribution drift checks (paid-to-date must be monotonic per claim across periods: needs the period model) |
| **Confidence inflation** | Current code sets AI confidence to 1.0 regardless of what the model returns (probe P18) | Keep the model's own confidence; calibrate against X-2 labels; never display 100% |

---

## 6. Business-model conclusion

- **Variable cost is negligible. People cost decides everything.** The
  product must make onboarding a new sender format fast (X-3) and keep
  support low (reliability). The AI model tier is a quality choice, not a
  margin choice.
- **The base case only works at ~30+ senders per customer and a
  ~£100/sender/month price point.** That is roughly a mid-market MA or a
  large MGA group. Both numbers are assumptions to test in X-8.
- **Early managed service** (TrueBind staff run the checks on customer files
  under NDA) is the fastest route to real files and revenue. It is not a
  scalable end state.
- **Nothing here is evidence that customers will pay.** It only shows the
  business is *not* structurally uneconomic if they do.
