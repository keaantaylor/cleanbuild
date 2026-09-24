# TrueBind — Competitive Landscape

Compiled 2026-09-24. Source IDs such as `[B5.2]` refer to
`TRUEBIND_SOURCE_REGISTER.md`. This file separates three kinds of statement:

- **DOC**: a capability described concretely on the vendor's own product
  page, standard or official document (fetched this session). This means the
  vendor documents it. It does *not* mean it was verified to work.
- **MKT**: a marketing claim, meaning an adjective, an unquantified
  superlative, or a self-reported metric with no method.
- **3P**: a statement from a third party (press or a competitor), noted
  with that party's interest.

Nothing here was verified hands-on. No competitor product was trialled in
this investigation. That is itself a gap, closed by experiment X-9 in
`TRUEBIND_STRATEGIC_ROADMAP.md`.

---

## 1. The structural fact that reshapes this market

**Lloyd's DDM is no longer mandatory.** DDM was the central bordereaux
processing platform (operated by LIMOSS and powered by Charles Taylor's
Tide). It was removed as a core market service, with a contractual end date
of **13 Sep 2024** [B2.1], and is now an **elective** service [B1.2]. The
Lloyd's DDM page now 301-redirects to the LIMOSS "DDM Elective" page. VIPR's
CEO, an interested party, says "all bar about six managing agents have
stepped away from DDM" [B2.1].

Consequences, with confidence:

1. **High.** Each managing agent now chooses its own tooling. The market is
   fragmenting across VIPR, Tide, distriBind, Verodat, Vellum, Send, Scrub
   AI, Xceedance, in-house builds and managed services.
2. **High.** The v5.2 standard defines *what* data is needed, not *how* it
   arrives: "Lloyd's has not mandated that a particular format is used for
   reporting" [B1.1]. Vellum's own FAQ says "Lloyd's 5.2 often varies
   significantly across managing agents, coverholders, and lines of
   business" [B5.4]. **Messy inbound spreadsheets are therefore a durable
   condition, not a transitional one.**
3. **Medium.** Vendors are converging on AI-assisted ingestion. Every
   significant platform now markets AI (VIPR "AI capabilities are live",
   Charles Taylor Bordereaux Sync "developed with Microsoft", Vellum
   "AI-native", Verodat "AI-ready"). **"We use AI to map columns" is table
   stakes, not a differentiator.**

---

## 2. Competitor profiles

### 2.1 Charles Taylor InsureTech: **Tide** and **Bordereaux Sync**

| Dimension | Finding |
|---|---|
| Company / product | Charles Taylor InsureTech. Tide is a bordereaux management platform and was the engine behind DDM. Bordereaux Sync is a standalone "AI tool" launched around June 2025 [B5.1]. |
| Customer / user | Lloyd's managing agents and DA teams (Tide). Bordereaux Sync positions as working with "ANY bordereaux management system" [B5.1]. |
| Inputs | DOC: bordereau files; DDM "maps, cleanses, and validates… outputs it in a standard format"; "inbuilt APIs within DDM can consume data from a variety of different sources" [B1.2]. |
| Workflow | DOC: Sync "screens all bordereau files and records within **before** transferring them" to a BMS [B5.1]. That is a **pre-ingestion assurance step, the same slot TrueBind targets.** |
| Standardisation | DOC: transforms to Lloyd's Coverholder Reporting Standards [B1.2]. |
| Validation | MKT: "spot errors and inconsistencies", "data cleansing and repair". No rule list published. |
| AI | MKT: "latest AI technology", "developed with Microsoft". No accuracy data. |
| Human review / exceptions / audit | Not documented on the fetched pages. |
| API | DOC: DDM/Tide "inbuilt APIs" [B1.2]. |
| Deployment | DOC: "cloud-based SaaS platform hosted in Azure" [B1.2]. |
| Pricing | Not public. |
| Differentiation | Incumbency (ran DDM); Microsoft partnership; a market-service heritage. |
| Limitations | Sync makes **"repair"** a selling point. Automatically *changing* data is the opposite of an evidence-first posture, and an audit-conscious buyer may object. |
| Apparent moat | Installed base from the DDM years, a Lloyd's-standard transformation library, and trust from the market-service role. |
| **Strategic threat** | **HIGH.** Bordereaux Sync occupies exactly the "screen before the BMS" position, is sold standalone, and has a Microsoft co-brand. |

### 2.2 **VIPR** Solutions (Portal, Intrali, Intarga, Data Cloud, Insights, Managed Services)

| Dimension | Finding |
|---|---|
| Company | UK DA-technology vendor. Homepage banner: "**Bridgepoint**… has completed a new majority investment" [B5.2]. Earlier backing by Tenzing was reported by a third party [B5.10]. |
| Customer / user | Managing agents, carriers, brokers (Acrisure Re named), MGAs [B5.2]. |
| Inputs | DOC: Intrali "import[s] and convert[s] multiple data formats to a single data standard"; the Portal supports direct submission [B5.2]. |
| Validation | DOC: "hundreds of checks and validations on the imported data referring to the **binder terms and previously processed data**" [B5.2]. That is contract-aware and history-aware validation, which **TrueBind does not have**. |
| AI | MKT: "VIPR's AI capabilities are live and deployed". |
| Human review / exceptions | MKT: query management in Managed Services. Not documented in detail. |
| Audit | Not documented on the fetched page. |
| API / integrations | DOC: "API-enabled data pipeline" with Portal plus Data Cloud; Data Cloud is "**built on Snowflake**" [B5.2]; partnership with Insurity (US program business) [B5.3]. |
| Business model | Platform licences plus **Managed Services** (outsourced bordereaux processing) [B5.2]. |
| Scale claims | MKT/self-reported: "processing in excess of 400,000 bordereaux per year… over 40% of Lloyd's syndicates" (2023) [B5.3]. A competitor blog says ">50% of MAs" [B5.10]. **The figures conflict, so treat them as unverified.** |
| Moat | Breadth across the DA lifecycle (onboarding, processing, data warehouse, analytics, managed service), installed base, PE funding. |
| Limitations | 3P (competitor, interested): "manual re-mapping required" when formats change [B5.10]. **Unverified.** |
| **Strategic threat** | **HIGH.** If VIPR's ingestion is "good enough", a point assurance tool struggles to get budget from VIPR customers unless it plugs *into* VIPR. |

### 2.3 **Vellum** Insurance

| Dimension | Finding |
|---|---|
| Positioning | "AI-native insurance data platform" for insurers, reinsurers, aggregators and MGAs [B5.4]. |
| Inputs | DOC: "spreadsheets, PDFs, emails, APIs, databases, and custom feeds" [B5.4]. |
| Standardisation | DOC: ingestion **and output** of Lloyd's 5.2, with an explicit acknowledgement that 5.2 varies in practice [B5.4]. |
| Coverage | DOC: premium, claims, risk exposure, payments, facultative, reinsurance, "IBNR and TPA fees" [B5.4]. |
| Validation | MKT/DOC: "hundreds of configurable validations", "configurable by feed", flags "guideline violations, mix shifts, and large losses in real time". |
| Human review / audit | **Not documented** on the pages fetched. |
| API | MKT: "API-first architecture". |
| Pricing / funding | Not public. |
| Limitations | Homepage counters render as "$0B"/"0M+" placeholders, so no public traction evidence. |
| Moat | Breadth of data model, including reinsurance and portfolio analytics. |
| **Strategic threat** | **MEDIUM–HIGH.** A broader product aimed at the same buyer, with portfolio intelligence on top. |

### 2.4 **Verodat**

| Dimension | Finding |
|---|---|
| Positioning | "Governed data supply chain" and "AI-ready data" for bordereaux [B5.5]. |
| Pricing | DOC (search snippet of the vendor page): "3 Week Trial – **€15,000** (fully redeemable if you continue)". DOC: "No per-binder fees" [B5.5]. **This is the only public price point found in the direct competitor set.** |
| Validation / audit | MKT: "built-in governance, validation, and audit trail capabilities". |
| **Strategic threat** | **MEDIUM.** Validates that buyers pay five-figure sums just to *trial* bordereaux automation, and competes on "governance". |

### 2.5 **distriBind**

| Dimension | Finding |
|---|---|
| Positioning | A digital data **exchange** between all parties, aiming to eliminate spreadsheet bordereaux; onboarding product "Sunapto" [B5.6]. |
| Customers | 3P: Liberty Specialty Markets, Allianz, Coral, Stere [B5.10]; testimonials from Otonomi and Stere on its site [B5.6]. |
| **Strategic threat** | **MEDIUM (long-term).** If exchange-at-source succeeds, the "messy spreadsheet" problem shrinks for participating chains. Adoption requires coverholder participation, which is historically slow. |

### 2.6 **Send** (Delegated Underwriting / Bordereaux Ingestion)

DOC [B5.7]: reporting schedules (expected vs missing submissions);
mapping to contract sections and sub-coverages; **interactive validation
against binder rules**; pre-agreed exceptions; structured policy generation.
Customer named: Argenta. **Threat: MEDIUM.** Contract-aware DA workflow is
a capability TrueBind lacks.

### 2.7 **Scrub AI**

[B5.8] (InsTech profile, 14 Mar 2025): ML cleansing plus a "ScrubHub"
warehouse; **API-only cleansing option**; flags breaches of binder
territorial limits. MKT: the industry spends "$2–$5 billion USD a year" on
repeated processing (vendor figure, no method). **Threat: MEDIUM.** It is
an API-first cleanser, close to an "assurance API".

### 2.8 Others seen but not examined (existence only)

Xceedance bordereaux management, Artificial Labs "Rapid Bordereaux
Extraction", Openkoda, TxMinds, V7 Go (document AI), Insurance Data
Solutions (MGA analytics), DataFlowMapper (mapping workbench) [B5.10,
B5.15, B5.16]. Not fetched and not profiled.

---

## 3. Adjacent categories

| Category | Examples | What they already do well | Why they don't simply win this market | Threat |
|---|---|---|---|---|
| Embeddable data importers / onboarding | OneSchema [B5.11], Flatfile ("Obvious") [B5.12], DataFlowMapper, Osmos | Column mapping UI, validation templates, 1M–10M-row files (OneSchema docs), self-hosting, per-credit pricing | No insurance semantics: no v5.2 field logic, binder terms, incurred decomposition or claim-period model | **MEDIUM.** A capable team could build a bordereaux product on them, or TrueBind could embed one. |
| Reconciliation platforms | Duco [B5.13], AutoRek, BlackLine | Matching engines, break management, audit, unstructured-data reconciliation (Duco, since Jul 2024) | Financial-markets or accounting-close focus; no bordereau semantics | **LOW–MEDIUM**, rising if they add insurance templates |
| Insurance intake / document AI | Cytora (acquired by Applied Systems) [B5.14], V7 Go, Hyperscience | LLM extraction from submissions, loss runs and claims documents | Focused on *new-business intake*, not periodic DA bordereaux assurance | **MEDIUM.** Adjacent motion, big distribution (Applied) |
| Data quality / observability | Great Expectations, Soda, Monte Carlo, Deequ [A2.3] | Declarative checks, anomaly detection over time, lineage | Operate *after* data is in a warehouse; no spreadsheet ingestion; no insurance rules | **LOW** directly. They are **design references** for "monitor forever". |
| Reinsurance data | Supercede | Cleans reinsurance submission data [search result] | Reinsurance placement focus | **LOW–MEDIUM** |
| Managed services / BPO | VIPR Managed Services, Xceedance, TPAs, offshore teams | Humans absorb the mess | Cost scales linearly with volume | This is the **real incumbent**: people plus Excel. |

---

## 4. Comparative capability matrix

Legend: ✅ documented, ◐ partial or claimed, ✖ not documented or absent,
? unknown. TrueBind's column is **verified in code** (see REVALIDATION §3),
which is a higher standard than the other columns.

| Capability | TrueBind (verified) | Tide / Sync | VIPR | Vellum | Verodat | Send | Scrub AI | Importers (OneSchema) |
|---|---|---|---|---|---|---|---|---|
| Multi-sheet, header-row detection | ✅ (≤50 rows) | ? | ? | ◐ | ? | ? | ◐ | ◐ |
| AI column mapping | ◐ (Haiku fallback, confidence discarded) | ◐ MKT | ◐ MKT | ◐ MKT | ◐ MKT | ✖ | ◐ | ✅ |
| Human mapping confirmation | ✅ | ? | ? | ? | ? | ◐ | ? | ✅ |
| Row-level exclusion *with* reasons | ✅ | ? | ? | ? | ? | ? | ? | ◐ |
| Row-count reconciliation | ✅ (but see §3: blind to truncation) | ? | ? | ? | ? | ? | ? | ✖ |
| Three-state "not evaluable" | ✅ | ? | ? | ? | ? | ? | ? | ✖ |
| **v5.2-correct incurred arithmetic** | **✖ (formula wrong vs CR0155)** | ◐ | ◐ | ◐ | ? | ? | ? | ✖ |
| Binder / contract-term validation | ✖ | ? | ✅ DOC | ◐ | ? | ✅ DOC | ◐ | ✖ |
| History-aware (vs previous period) | ✖ | ? | ✅ DOC | ◐ ("mix shifts") | ? | ✖ | ◐ ("learns") | ✖ |
| Reporting-period / submission schedule | ✖ | ? | ◐ | ? | ? | ✅ DOC | ? | ✖ |
| Premium / risk bordereaux | ✖ (claims only) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | n/a |
| Multi-tenant auth, SSO | ✖ | ✅ (assumed, SaaS) | ✅ | ? | ? | ? | ? | ✅ |
| Data warehouse output | ✖ | ✅ | ✅ Snowflake | ◐ | ✅ | ◐ | ✅ ScrubHub | ✖ |
| API | ✖ (internal REST only, no auth) | ✅ | ✅ | ◐ | ? | ? | ✅ | ✅ |
| Public price | — | ✖ | ✖ | ✖ | ✅ €15k trial | ✖ | ✖ | ✅ |

**Reading the matrix honestly.** TrueBind is *behind* on breadth (claims
only, no contract terms, no history, no auth, no API, no warehouse). Its
only candidate differentiators are the **explicit refusal-to-guess
semantics**: not-evaluable as a first-class state, excluded rows with
reasons, row-count reconciliation, and a human-confirmed mapping with
provenance. Competitors do not *document* these, but "not documented" is
not "absent". Nobody knows whether Tide or VIPR already do them internally.
The differentiator is **unverified relative to competitors**.

---

## 5. Where the competitive gap probably is

Hypotheses only. Evidence strength is noted, and each links to an
experiment in the roadmap.

| # | Hypothesis | Evidence for | Evidence against | Confidence |
|---|---|---|---|---|
| G1 | Buyers lack an **independent, evidence-producing check** that sits *between* the coverholder's file and the BMS, and says what it could *not* verify. | v5.2 allows any format [B1.1]; the CUO calls stale data "bizarre" [B2.2]; the Solvency II data-quality duty [B3.1]; automation-bias literature says unflagged problems get missed [A3.4, A3.5]. | Charles Taylor now sells exactly this slot (Bordereaux Sync) [B5.1]. VIPR claims "hundreds of checks" [B5.2]. | **Medium.** The slot exists; whether it is *unfilled* is unknown. |
| G2 | Incumbent BMSs **re-map by hand** when a coverholder's format changes. | Only competitor content marketing says so [B5.10]; InsTech says standardisation doesn't fix source data [B5.9]. | No first-hand evidence. | **Low.** Needs customer interviews (X-1). |
| G3 | Buyers distrust AI that "repairs" data and prefer AI that **proposes** while deterministic rules decide. | Lee & See [A3.1]; Bansal et al. show explanations raise acceptance even when the AI is wrong [A3.12]; financial reporting accountability; Solvency II "accurate/complete/appropriate" [B3.1]. | Sync, and some competitors, sell "repair" as a feature and it may be what buyers ask for. | **Medium–Low.** Plausible from the literature; untested with buyers. |
| G4 | Mid-size MGAs, coverholders and smaller MAs are priced out of VIPR/Tide-class platforms. | The only public price is €15k just for a *trial* [B5.5]; enterprise sales everywhere. | No price data for VIPR or Tide; some vendors may have SME tiers. | **Low–Medium.** |
| G5 | The **sender side** (coverholders and TPAs *preparing* bordereaux) is under-served: submission-readiness checking before sending. | Lloyd's DA oversight pressure and coverholder removals [B2.2, B2.3]; lateness and quality are the review triggers (T4 only). | distriBind and VIPR Portal target senders; uptake is unknown. | **Low–Medium.** |

---

## 6. Implications for TrueBind

1. **Do not compete as a bordereaux management system.** VIPR, Tide and Vellum
   are years ahead on breadth, and the market is already procuring
   post-DDM. There is no evidence TrueBind can win a BMS bake-off.
2. **The only defensible wedge the evidence supports is
   "assurance-grade ingestion": a verifiable, refuse-to-guess check that
   produces an evidence pack.** It is only a moat if it is (a) *correct
   against the v5.2 standard*, which it currently is not (§3 of the
   revalidation), (b) *faster to onboard a new coverholder format* than an
   incumbent (unmeasured), and (c) *pluggable into* VIPR, Tide and
   Snowflake rather than a replacement for them.
3. **Charles Taylor's Bordereaux Sync is the most direct threat** and must be
   evaluated hands-on before any positioning decision (roadmap X-9).
4. **Pricing anchor:** the only public data point (€15k trial, Verodat) implies
   buyers expect five-figure annual contracts. A per-file SaaS price at
   OneSchema-like levels would under-price the segment; a £50k+ enterprise
   price would require breadth TrueBind doesn't have. See
   `TRUEBIND_UNIT_ECONOMICS.md`.
