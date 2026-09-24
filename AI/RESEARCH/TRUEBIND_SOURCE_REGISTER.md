# TrueBind — Source Register

Compiled 2026-09-24 during the product-revalidation investigation
(`TRUEBIND_PRODUCT_REVALIDATION.md`). Every external source cited in any
`AI/RESEARCH/*.md` file is listed here.

## How this register was built

- **Every DOI in Section A was resolved against the Crossref API**
  (`api.crossref.org/works/{doi}`) during this session. Title, authors, year,
  and venue below come from that response, not from memory. Two citations
  I had recalled from memory were **wrong** and were corrected by this step:
  - `10.1145/3276512` is *not* ExceLint. It resolves to an unrelated
    points-to-analysis paper. ExceLint's actual DOI is `10.1145/3276518`.
  - Ziemann et al. (2016): the third author is **El-Osta**, not "El-Mahgary".
- arXiv items were verified through the Firecrawl research index
  (`firecrawl_research_inspect_paper`), which returns the arXiv record.
- Web sources were fetched (WebFetch or Firecrawl scrape) during this session.
  Where a page could not be fetched (HTTP 401/403), that is recorded. Claims
  from unfetched pages are marked as coming from a search snippet, and none
  carries a conclusion on its own.
- **"Peer-reviewed"** is used only where the venue is a refereed journal or a
  refereed conference proceedings, per the Crossref record type
  (`journal-article` / `proceedings-article` at a known refereed venue).
  arXiv preprints are labelled **preprint (not peer-reviewed)**, even when
  widely cited.

Tiers follow the brief: **T1** peer-reviewed / regulator / standards body /
government / official Lloyd's-LMA-ACORD material; **T2** primary company or
product documentation; **T3** reputable industry or professional-body
analysis; **T4** press, blogs, vendor content marketing, forums.

---

## A. Peer-reviewed and scholarly research

### A1. Spreadsheet error, auditing and anomaly detection

| # | Source | Type / Tier | Date | DOI / URL | Claim supported | Strength | Limitation |
|---|---|---|---|---|---|---|---|
| A1.1 | Panko, R. R. "What We Know About Spreadsheet Errors." *Journal of Organizational and End User Computing* | Journal, T1 | 1998 | 10.4018/joeuc.1998040102 | Spreadsheet errors are common. Field audits and experiments repeatedly find errors in a large share of spreadsheets, and error rates per cell are low but non-trivial, so large sheets almost always contain errors. | Foundational review, widely replicated. | Aggregates older studies (1990s). Mostly *formula-development* errors, not data-ingestion errors. |
| A1.2 | Panko, R. R.; Aurigemma, S. "Revising the Panko–Halverson taxonomy of spreadsheet errors." *Decision Support Systems* 49(2) | Journal, T1 | 2010 | 10.1016/j.dss.2010.02.009 | Error taxonomy: mechanical, logic and omission errors, and qualitative vs quantitative. Violations are distinguished from errors. | Refereed taxonomy, used in later work. | A classification scheme, not a measured prevalence. |
| A1.3 | Powell, S. G.; Baker, K. R.; Lawson, B. "A critical review of the literature on spreadsheet errors." *Decision Support Systems* 46(1) | Journal, T1 | 2008 | 10.1016/j.dss.2008.06.001 | Much earlier "error rate" research used inconsistent definitions. Prevalence claims should be treated cautiously. | Critical review; tempers overstatement. | Shows the evidence base is heterogeneous. Cuts both ways for a vendor pitch. |
| A1.4 | Powell, S. G.; Baker, K. R.; Lawson, B. "Errors in Operational Spreadsheets." *Journal of Organizational and End User Computing* 21(3) | Journal, T1 | 2009 | 10.4018/joeuc.2009070102 | Audits of real operational spreadsheets found errors in most, with a minority having material (quantitative) impact. | Field audit of real workbooks. | Small sample of organisations. Formula errors, not bordereaux ingestion. |
| A1.5 | Galletta, D. F. et al. "An empirical study of spreadsheet error-finding performance." *Accounting, Management and Information Technologies* 3(2) | Journal, T1 | 1993 | 10.1016/0959-8022(93)90001-M | Even experienced users detect only part of the seeded errors when reviewing spreadsheets. Human inspection alone is an unreliable control. | Controlled experiment. | Lab setting and old tooling, but the direction has been replicated. |
| A1.6 | Hermans, F.; Murphy-Hill, E. "Enron's Spreadsheets and Related Emails: A Dataset and Analysis." ICSE 2015 (SEIP) | Conference, T1 | 2015 | 10.1109/ICSE.2015.129 | A large real corporate corpus (~15k spreadsheets) shows spreadsheets are central to financial operations and are exchanged by email, with errors and error-related correspondence. | Real-world corpus at scale. | One company (energy trading), pre-2002. |
| A1.7 | Hermans, F.; Pinzger, M.; van Deursen, A. "Detecting and refactoring code smells in spreadsheet formulas." *Empirical Software Engineering* | Journal, T1 | 2014 | 10.1007/s10664-013-9296-2 | Automated static analysis can surface risky spreadsheet structures that humans miss. | Refereed; tool plus evaluation. | Formula smells. TrueBind reads values, not formulas. |
| A1.8 | Barowy, D. W.; Gochev, D.; Berger, E. D. "CheckCell: data debugging for spreadsheets." OOPSLA 2014 | Conference, T1 | 2014 | 10.1145/2660193.2660207 | "Data debugging": automatically finding input *values* with disproportionate impact on outputs is feasible and catches errors humans miss. **This is the closest academic analogue to value-level assurance.** | Refereed PL venue, with evaluation. | Research prototype; single-workbook scope. |
| A1.9 | Barowy, D. W.; Berger, E. D.; Zorn, B. "ExceLint: automatically finding spreadsheet formula errors." *Proc. ACM Program. Lang.* (OOPSLA) | Journal, T1 | 2018 | 10.1145/3276518 | Structure-aware anomaly detection finds formula errors with useful precision. | Refereed. | Formula errors, not ingestion. |
| A1.10 | Cheung, S.-C. et al. "CUSTODES: automatic spreadsheet cell clustering and smell detection." ICSE 2016 | Conference, T1 | 2016 | 10.1145/2884781.2884796 | Cell clustering detects inconsistent cells in spreadsheet tables. | Refereed. | Formula and cell smells. |
| A1.11 | Herndon, T.; Ash, M.; Pollin, R. "Does high public debt consistently stifle economic growth? A critique of Reinhart and Rogoff." *Cambridge Journal of Economics* 38(2) | Journal, T1 | 2014 | 10.1093/cje/bet075 | A high-profile real consequence: a spreadsheet range-selection error, plus data exclusions, materially changed a policy-relevant result. | Refereed replication. | A single case, so illustrative only. |
| A1.12 | Ziemann, M.; Eren, Y.; El-Osta, A. "Gene name errors are widespread in the scientific literature." *Genome Biology* 17 | Journal, T1 | 2016 | 10.1186/s13059-016-1044-7 | **Silent type coercion** (Excel converting gene symbols to dates) corrupted data in about 20% of the papers with Excel gene lists that were screened. This is directly analogous to TrueBind's verified date and amount coercion risks (see REVALIDATION §4, P5/P6). | Refereed; large screened sample. | Different domain, same mechanism. |
| A1.13 | Dong, H. et al. "TableSense: Spreadsheet Table Detection with Convolutional Neural Networks." AAAI 2019 | Conference, T1 | 2019 | 10.1609/aaai.v33i01.330169 | Table and header detection in real spreadsheets is a hard, non-trivial ML problem; heuristics miss many layouts. | Refereed; Microsoft-scale corpus. | Evaluated on its own corpus. |

### A2. Data quality, schema matching, entity resolution

| # | Source | Type / Tier | Date | DOI / URL | Claim supported | Strength | Limitation |
|---|---|---|---|---|---|---|---|
| A2.1 | Wang, R. Y.; Strong, D. M. "Beyond Accuracy: What Data Quality Means to Data Consumers." *JMIS* 12(4) | Journal, T1 | 1996 | 10.1080/07421222.1996.11518099 | Data quality is multi-dimensional: intrinsic, contextual, representational and accessibility. "Fitness for use" is consumer-defined. | Foundational; highly cited. | Conceptual framework, not a measurement of any product. |
| A2.2 | Batini, C. et al. "Methodologies for data quality assessment and improvement." *ACM Computing Surveys* 41(3) | Journal, T1 | 2009 | 10.1145/1541880.1541883 | Structured DQ assessment methodologies exist. Completeness, accuracy, consistency and timeliness are the standard dimensions. | Survey. | Pre-LLM. |
| A2.3 | Schelter, S. et al. "Automating large-scale data quality verification." *PVLDB* 11(12) | Journal, T1 | 2018 | 10.14778/3229863.3229867 | Declarative, unit-test-style data constraints plus incremental metrics and anomaly detection work at scale (Amazon Deequ). This is the model for "Map once, monitor forever". | Refereed plus production use. | Engineering system paper. |
| A2.4 | Rahm, E.; Bernstein, P. A. "A survey of approaches to automatic schema matching." *VLDB Journal* 10(4) | Journal, T1 | 2001 | 10.1007/s007780100057 | Schema matching combines name, instance and constraint evidence. **Name-only matching is known to be weak.** TrueBind's alias matching is name-only. | Foundational. | Pre-LLM. |
| A2.5 | Parciak, M. et al. "Schema Matching with Large Language Models: an Experimental Study." arXiv:2407.11852 | **Preprint (not peer-reviewed)**, T3 | 2024 | arxiv.org/abs/2407.11852 | Off-the-shelf LLMs can bootstrap schema matching from names and descriptions only. Quality is sensitive to how much context is given, and "verification effort" is a first-class metric. | Controlled benchmark. | Health-domain schemas; preprint. |
| A2.6 | Fellegi, I. P.; Sunter, A. B. "A Theory for Record Linkage." *JASA* 64(328) | Journal, T1 | 1969 | 10.1080/01621459.1969.10501049 | Probabilistic record linkage gives match / possible-match / non-match regions with **explicit error-rate trade-offs**. TrueBind's dedupe has fixed thresholds and no error model. | Foundational. | — |
| A2.7 | Christen, P. "A Survey of Indexing Techniques for Scalable Record Linkage and Deduplication." *IEEE TKDE* 24(9) | Journal, T1 | 2012 | 10.1109/TKDE.2011.127 | Blocking choice dominates both recall and cost. Single short-prefix blocking is a known weak point (block sizes grow with data). This is consistent with the super-linear dedupe time measured here (REVALIDATION §5). | Survey. | — |
| A2.8 | Papadakis, G. et al. "Blocking and Filtering Techniques for Entity Resolution: A Survey." *ACM Computing Surveys* 53(2) | Journal, T1 | 2021 (Crossref year) | 10.1145/3377455 | A modern survey of blocking, meta-blocking and filtering to bound comparisons. | Survey. | — |

### A3. Human–automation trust, reliance, and explanation

| # | Source | Type / Tier | Date | DOI / URL | Claim supported | Strength | Limitation |
|---|---|---|---|---|---|---|---|
| A3.1 | Lee, J. D.; See, K. A. "Trust in Automation: Designing for Appropriate Reliance." *Human Factors* 46(1) | Journal, T1 | 2004 | 10.1518/hfes.46.1.50_30392 | The design goal is **calibrated** trust (trust matching actual reliability), not maximal trust. Displays should make an automation's purpose, process and performance visible. | Foundational; highly cited. | Conceptual plus review. |
| A3.2 | Parasuraman, R.; Riley, V. "Humans and Automation: Use, Misuse, Disuse, Abuse." *Human Factors* 39(2) | Journal, T1 | 1997 | 10.1518/001872097778543886 | Over-reliance (misuse) and under-reliance (disuse) are both failure modes. | Foundational. | — |
| A3.3 | Parasuraman, R.; Manzey, D. H. "Complacency and Bias in Human Use of Automation: An Attentional Integration." *Human Factors* 52(3) | Journal, T1 | 2010 | 10.1177/0018720810376055 | Automation bias and complacency occur in experts as well as novices, and **are not eliminated by training**. They increase with reliability and workload. | Integrative review. | — |
| A3.4 | Mosier, K. L. et al. "Automation Bias: Decision Making and Performance in High-Tech Cockpits." *Int. J. Aviation Psychology* 8(1) | Journal, T1 | 1998 | 10.1207/s15327108ijap0801_3 | Experienced operators make omission errors (missing unflagged problems) and commission errors (following wrong automated advice). | Refereed experiment. | Aviation domain. |
| A3.5 | Skitka, L. J.; Mosier, K. L.; Burdick, M. "Does automation bias decision-making?" *Int. J. Human-Computer Studies* 51(5) | Journal, T1 | 1999 | 10.1006/ijhc.1999.0252 | People with an automated aid missed events the aid failed to flag **more often** than people without it. **"Green" screens can hide unflagged defects.** | Refereed experiment. | Lab task. |
| A3.6 | Goddard, K.; Roudsari, A.; Wyatt, J. C. "Automation bias: a systematic review of frequency, effect mediators, and mitigators." *JAMIA* 19(1) | Journal, T1 | 2012 | 10.1136/amiajnl-2011-000089 | Automation bias is frequent in clinical decision support. Mitigators include decision-support design, presenting uncertainty, and accountability. | Systematic review. | Clinical domain. |
| A3.7 | Hoff, K. A.; Bashir, M. "Trust in Automation: Integrating Empirical Evidence on Factors That Influence Trust." *Human Factors* 57(3) | Journal, T1 | 2015 | 10.1177/0018720814547570 | Trust has dispositional, situational and learned layers. Error visibility and feedback shape learned trust. | Systematic review (127 studies). | — |
| A3.8 | Dietvorst, B. J.; Simmons, J. P.; Massey, C. "Algorithm aversion." *J. Experimental Psychology: General* 144(1) | Journal, T1 | 2015 | 10.1037/xge0000033 | People abandon algorithms after seeing them err, even when the algorithm beats humans. **One visible false positive can cost adoption.** | Refereed experiments. | Forecasting tasks. |
| A3.9 | Amershi, S. et al. "Guidelines for Human-AI Interaction." CHI 2019 | Conference, T1 | 2019 | 10.1145/3290605.3300233 | 18 validated guidelines, e.g. "make clear how well the system can do what it can do", "support efficient correction", "remember recent interactions", "convey the consequences of user actions". | Refereed; validated with 49 practitioners. | Guidelines, not effect sizes. |
| A3.10 | Kocielnik, R.; Amershi, S.; Bennett, P. N. "Will You Accept an Imperfect AI?" CHI 2019 | Conference, T1 | 2019 | 10.1145/3290605.3300641 | Setting expectations about accuracy up front changes acceptance. Tuning for **false positives vs false negatives** changes perceived quality at equal accuracy. | Refereed experiment. | Scheduling-assistant task. |
| A3.11 | Zhang, Y.; Liao, Q. V.; Bellamy, R. K. E. "Effect of confidence and explanation on accuracy and trust calibration in AI-assisted decision making." FAT* 2020 | Conference, T1 | 2020 | 10.1145/3351095.3372852 | Showing **per-case confidence** helps trust calibration. Explanations alone did not improve calibration in that setting. | Refereed experiment. | Specific task. |
| A3.12 | Bansal, G. et al. "Does the Whole Exceed its Parts? The Effect of AI Explanations on Complementary Team Performance." CHI 2021 | Conference, T1 | 2021 | 10.1145/3411764.3445717 | Explanations increased acceptance of AI advice **whether or not the AI was right**. They did not reliably improve team accuracy over showing confidence. | Refereed experiment. | Specific tasks. |
| A3.13 | Buçinca, Z.; Malaya, M. B.; Gajos, K. Z. "To Trust or to Think: Cognitive Forcing Functions Can Reduce Overreliance on AI." PACM HCI (CSCW) 5 | Journal, T1 | 2021 | 10.1145/3449287 | "Cognitive forcing" (asking the human to decide before seeing the AI answer, or adding deliberate friction) reduces over-reliance, at some cost to satisfaction. | Refereed experiment. | Nutrition task. |
| A3.14 | Vasconcelos, H.; Jörke, M.; Grunde-McLaughlin, M.; Gerstenberg, T.; Bernstein, M.; Krishna, R. "Explanations Can Reduce Overreliance on AI Systems During Decision-Making." PACM HCI (CSCW) | Journal, T1 | 2023 | 10.1145/3579605 | Over-reliance falls when verifying the AI is made cheap relative to the cost of doing the task. Explanations help when they make verification easier. | Refereed experiments. | Maze and puzzle tasks. |

### A4. AI coding agents, benchmarks, test adequacy

| # | Source | Type / Tier | Date | DOI / URL | Claim supported | Strength | Limitation |
|---|---|---|---|---|---|---|---|
| A4.1 | Jimenez, C. E. et al. "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?" arXiv:2310.06770 (ICLR 2024) | Refereed conference (ICLR 2024; arXiv version inspected), T1 | 2023/2024 | arxiv.org/abs/2310.06770 | The standard issue-resolution benchmark; tests decide success. | Refereed venue. | Later shown to have weak or contaminated tests (A4.3–A4.5). |
| A4.2 | Deng, X. et al. "SWE-Bench Pro: Can AI Agents Solve Long-Horizon Software Engineering Tasks?" arXiv:2509.16941 | **Preprint**, T2/T3 (Scale AI) | 2025 | arxiv.org/abs/2509.16941 | 1,865 long-horizon tasks from 41 repos, with public, held-out and commercial splits to resist contamination. | Larger and harder than Verified. | Preprint. A third party reports a git-history reward-hacking issue (T4; see B6.4). |
| A4.3 | Wang, Y.; Pradel, M.; Liu, Z. "Are 'Solved Issues' in SWE-bench Really Solved Correctly? An Empirical Study." arXiv:2503.15223 | **Preprint** | 2025 | arxiv.org/abs/2503.15223 | 7.8% of "passing" patches fail the full developer test suite. **29.6% of plausible patches behave differently from ground truth.** Reported resolution rates are inflated by 6.2 points. **Passing tests ≠ correct.** | Differential testing (PatchDiff). | Preprint; three tools studied. |
| A4.4 | Aleithan, R. et al. "SWE-Bench+: Enhanced Coding Benchmark for LLMs." arXiv:2410.06992 | **Preprint** | 2024 | arxiv.org/abs/2410.06992 | 32.67% of "successful" patches involved solution leakage and 31.08% passed only because tests were weak. The filtered resolution rate fell from 12.47% to 3.97%. | Manual screening. | Preprint; one agent/model pair. |
| A4.5 | OpenAI. "Why SWE-bench Verified no longer measures frontier coding capabilities." | Company research note, T2 | 23 Feb 2026 | openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/ | Audit of 138 hard Verified tasks: 59.4% had material test or spec issues (35.5% "narrow" tests rejecting correct solutions; 18.8% "wide" tests checking unspecified behaviour). Frontier models could reproduce gold patches, i.e. contamination. OpenAI stopped reporting Verified. | Primary source from a benchmark co-creator. | Self-reported audit. |
| A4.6 | Fakhoury, S. et al. "LLM-Based Test-Driven Interactive Code Generation: User Study and Empirical Evaluation." *IEEE TSE* | Journal, T1 | 2024 | 10.1109/TSE.2024.3428972 | Having users confirm or refute generated **tests** before accepting code (TiCoder) improved correctness and reduced cognitive load. | Refereed; user study plus benchmarks. | Function-level tasks. |
| A4.7 | Becker, J. et al. (METR). "Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity." arXiv:2507.09089 | **Preprint** (RCT) | 2025 | arxiv.org/abs/2507.09089 | RCT: 16 experienced developers, 246 tasks. AI access **increased** completion time by 19%, while developers *believed* it reduced time by 20%. **Perceived agent productivity is not measured productivity.** | Randomised design. | Small n; early-2025 tools; mature repos. |

---

## B. Industry, regulatory and standards sources

### B1. Lloyd's, LIMOSS, Velonetic, LMA (official)

| # | Source | Type / Tier | Date | URL | Claim supported | Strength | Limitation |
|---|---|---|---|---|---|---|---|
| B1.1 | Lloyd's. *Coverholder Reporting Standards User Guide, Version 5.2* (118 pp.) | Official standard, T1 | 20 Aug 2019 | assets.lloyds.com/…/pdf-reporting-standards-lloyds-coverholder-reporting-standards-user-guide-V52.pdf | (i) The standard defines a **core data set**, and "**Lloyd's has not mandated that a particular format is used for reporting**". (ii) Claims field codes include CR0126 *Paid this month – Indemnity*, CR0128 *Previously Paid – Indemnity*, CR0130 *Reserve – Indemnity*, CR0134 *Total Incurred – Indemnity*. (iii) **CR0155 Total Incurred = paid this month indemnity + previously paid indemnity + reserve indemnity + the same three for fees** (quoted verbatim in REVALIDATION §3). (iv) "ACORD standards may be used to provide the information." | Primary standard, fetched and quoted. | 2019 document. Class-specific (LM TOM) and local-office additions sit outside it. |
| B1.2 | LIMOSS. "Delegated Data Manager – DDM Elective" | Official market-service page, T1 | fetched 2026-09-24 | limoss.london/ddm (the lloyds.com DDM page 301-redirects here) | DDM is now an **elective** service for managing agents that want it. It "maps, cleanses, and validates bordereaux data and then outputs it in a standard format". It is powered by Tide (Azure SaaS) and has inbuilt APIs. | Primary. | Gives no adoption numbers or dates. |
| B1.3 | Velonetic Blueprint Two pages ("DDM", "DA data strategy") | Official, T1 | — | velonetic.co.uk/blueprint-two/… | — | — | **Returned HTTP 403 "Access denied" on every attempt (WebFetch and Firecrawl stealth proxy).** No claim in this investigation rests on them. |
| B1.4 | Lloyd's flyer, "2026 Market Update – Adoption of Delegated Data Manager" (asset filename says 2026) | Official, T1 | undated in text | assets.lloyds.com/…/Canada Chronicle 2026 Market Update.pdf | Describes a *phased approach to full adoption* of DDM and DDM as "the centralised data source". | Primary. | **Content reads as pre-2024 (pre-elective) despite the filename. Treated as historical and superseded by B1.2/B2.1.** |

### B2. Press and interviews on the DDM mandate and Lloyd's DA oversight

| # | Source | Type / Tier | Date | URL | Claim supported | Strength | Limitation |
|---|---|---|---|---|---|---|---|
| B2.1 | Wallace, M. "Post the DDM mandate – where do Lloyd's managing agents and brokers go next?" *Insurance Business* | Trade press, T4 | 4 Sep 2024 | insurancebusinessmag.com/uk/news/technology/…-504127.aspx | DDM was removed as a core market service, with a contractual end date of **13 Sep 2024**. VIPR's CEO says "all bar about six managing agents have stepped away from DDM". One MA spent about 0.25% of GWP (>£1m/yr) on data collection. | Dated, named sources. | The quantitative claims come from a **competing vendor's CEO** (VIPR), who has an interest. |
| B2.2 | Howard, L. S. "Lloyd's Focuses on Delegated Authority Arrangements…" *Insurance Journal* | Trade press quoting Lloyd's CUO, T3/T4 | 21 Oct 2024 | insurancejournal.com/magazines/mag-features/2024/10/21/797417.htm | Lloyd's CUO Rachel Turk: "**Currently 39% of gross written premium is generated through delegated arrangements**", and it is "bizarre" that syndicates "are still receiving bordereau data that is out of date". Poor DA performance "was one of the contributors to the deteriorating loss ratio from 2013 onwards". | Direct quotes from Lloyd's CUO at the Q3 2024 briefing. | Secondary report of a speech. |
| B2.3 | Banks, R. "Lloyd's removes a coverholder around every two months over behaviour concerns: Turk." *The Insurer* | Trade press, T4 | 5 Sep 2026 | theinsurer.com/… | Headline only: Lloyd's actively removes coverholders. | — | **Paywalled (HTTP 401). Headline only; no claim relies on the body.** |
| B2.4 | Charles Taylor. "Tide: What's next for DDM?" | Vendor news, T2 | undated | charlestaylor.com/en/news/news-post/tide-whats-next-for-ddm/ | Confirms DDM has exited as a core market service. Tide continues. | Primary for the vendor's own position. | Promotional; no numbers. |

### B3. Regulation and professional bodies

| # | Source | Type / Tier | Date | URL | Claim supported | Strength | Limitation |
|---|---|---|---|---|---|---|---|
| B3.1 | EIOPA Single Rulebook: Commission Delegated Regulation (EU) 2015/35, **Art. 19** "Data used in the calculation of technical provisions", implementing Directive 2009/138/EC **Art. 82** | Regulation, T1 | 2015 | eiopa.europa.eu/rulebook/solvency-ii-single-rulebook/article-2432_en | Insurers must ensure the data used for technical provisions is **complete, accurate and appropriate**, under defined conditions. This is the regulatory root of the demand for "data assurance" in reserving. | Primary regulation. | EU text. UK firms are now under PRA "Solvency UK" rules (successor regime), which were not separately fetched. |
| B3.2 | FCA. "Insurance multi-firm review of outcomes monitoring under the Consumer Duty" | Regulator, T1 | 26 Jun 2024 (per secondary summaries) | fca.org.uk/publications/multi-firm-reviews/insurance-multi-firm-review-outcomes-monitoring-under-consumer-duty | Under the Duty, firms must "regularly assess, test, understand and evidence the outcomes their customers are receiving". Many insurers needed improvements. This implies demand for **evidenced**, data-driven oversight, including over distribution chains. | Primary regulator page (search result plus summaries). | Page not fully fetched. Links to bordereaux data are an inference, not an FCA statement. |
| B3.3 | IFoA GIRO Data Quality Working Party. "Data Quality Working Party Paper" | Professional body, T3 | 2006 | actuaries.org.uk/documents/report-data-quality-working-party-2006 | Survey: **mean 26%, median 25% of actuarial time** spent on data quality issues (n=38; insurer/reinsurer subgroup n=15, median 20%). | Primary survey tables quoted. | Small n; 2006. |
| B3.4 | NIST. *AI Risk Management Framework 1.0* (NIST AI 100-1) and *Generative AI Profile* (NIST AI 600-1) | Government standard, T1 | Jan 2023 / Jul 2024 | nist.gov/itl/ai-risk-management-framework | Govern / Map / Measure / Manage functions. GenAI risks include confabulation, information integrity and value-chain risk. | Primary framework. | **Not re-fetched this session.** Cited for structure only. |

### B4. Security primary guidance

| # | Source | Type / Tier | Date | URL | Claim supported | Strength | Limitation |
|---|---|---|---|---|---|---|---|
| B4.1 | OWASP File Upload Cheat Sheet | Standards community, T1/T2 | fetched 2026-09-24 | cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html | Allowlist extensions; don't trust Content-Type; **generate server-side filenames**; enforce size limits, including decompressed size for ZIP containers; store outside the webroot; require authentication before upload; AV/CDR. | Primary. | Generic. |
| B4.2 | OWASP Top 10 for LLM Applications 2025 | Standards community, T1/T2 | 2025 | genai.owasp.org/llm-top-10/ | LLM01 Prompt Injection; LLM02 Sensitive Information Disclosure; LLM03 Supply Chain; LLM04 Data and Model Poisoning; LLM05 Improper Output Handling; LLM06 Excessive Agency; LLM09 Misinformation; LLM10 Unbounded Consumption. | Primary. | — |
| B4.3 | openpyxl documentation, security note | Library docs, T2 | fetched 2026-09-24 | openpyxl.readthedocs.io | "By default openpyxl does not guard against quadratic blowup or billion laughs xml attacks. To guard against these attacks install defusedxml." **`defusedxml` is not a TrueBind dependency (verified: not importable in the project venv; `openpyxl.xml.DEFUSEDXML == False`).** | Primary. | — |
| B4.4 | OWASP "CSV Injection" | Standards community, T2 | not re-fetched | owasp.org/www-community/attacks/CSV_Injection | Cells beginning `=`, `+`, `-` or `@` are executed as formulas by spreadsheet apps. Exports must neutralise them. | Well known. | Not re-fetched this session. |

### B5. Competitor and adjacent-vendor documentation (T2 unless marked)

| # | Source | Date fetched | URL | What was documented | Limitation |
|---|---|---|---|---|---|
| B5.1 | Charles Taylor, *Bordereaux Sync* product page | 2026-09-24 | charlestaylor.com/en/insuretech/bordereaux-sync/ | Standalone SaaS, "developed with Microsoft". Screens bordereau files and records *before* they reach Tide "or ANY bordereaux management system", for "data cleansing and repair". | Marketing page; no accuracy data. |
| B5.2 | VIPR homepage and Intrali page | 2026-09-24 | viprsolutions.com; …/products/intrali | Portal, Intrali (ingestion plus "hundreds of checks and validations… referring to the binder terms and previously processed data"), Intarga (onboarding), Data Cloud (**built on Snowflake**), Insights, Managed Services. **Bridgepoint majority investment** (homepage banner). | Adoption figures conflict across VIPR sources (2023 press release "over 40% of Lloyd's syndicates"; third-party blog ">50% of MAs"; garbled homepage counters). Treated as unverified. |
| B5.3 | Insurity × VIPR press release | 9 May 2023 | insurity.com/press-release/… | "processing in excess of 400,000 bordereaux per year". | Vendor self-report. |
| B5.4 | Vellum Insurance platform and bordereaux pages | 2026-09-24 | velluminsurance.com/platform/ | Ingests "spreadsheets, PDFs, emails, APIs, databases"; "hundreds of configurable validations"; supports ingestion **and output** of Lloyd's 5.2, noting that "Lloyd's 5.2 often varies significantly across managing agents, coverholders, and lines of business". Premium, claims, risk, payments, facultative and RI bordereaux. | Homepage metric counters render as "$0B"/"0M+" placeholders. No audit or HITL documentation found. |
| B5.5 | Verodat bordereaux pages | 2026-09-24 | verodat.com/solutions/bordereaux-management/ ; …/bordereaux-pricing-disruption/ | "3 Week Trial – **€15,000** (fully redeemable if you continue)" (search snippet of the solution page). Pricing page: "No per-binder fees". | The price comes from a search snippet of the vendor page; the pricing page itself gives no figures. |
| B5.6 | distriBind homepage | 2026-09-24 | distribind.io | Positions as a data **exchange** between all parties that "eliminate[s] spreadsheets". Onboarding product "Sunapto". | Testimonials only. |
| B5.7 | Send, Bordereaux Ingestion | 2026-09-24 | send.technology/platform/bordereaux-ingestion/ | Reporting schedules (expected vs missing submissions), section/sub-coverage mapping, **validation against binder rules**, pre-agreed exception handling. | No AI or format details. |
| B5.8 | InsTech, "Scrub AI: transforming DA data with AI-driven cleansing" | 14 Mar 2025 | instech.co/knowledge-centre/… | ML cleansing plus "ScrubHub" warehouse; API-only option; flags out-of-territory / binder-terms breaches. Scrub AI claims the industry spends "$2–$5 billion USD a year" on repeated data processing. | T3/T4 (sponsored-style profile). The $ figure is the vendor's own. |
| B5.9 | InsTech, Quiana, S. "The Bordereaux Bottleneck" | 26 Oct 2025 | instech.co/knowledge-centre/… | Reporting lags of "30, 60, or even 90 days"; formats include "Excel, csv, txt, xml or database backup files"; standardisation "address[es] destination requirements rather than source data infrastructure". | T3; qualitative, with no sample sizes. |
| B5.10 | DataFlowMapper blog, "VIPR Alternative for Bordereaux Processing Compared" | 18 Mar 2026 | dataflowmapper.com/blog/vipr-alternative-bordereaux-processing | Market narrative: DDM became elective in Sep 2024, followed by an active procurement cycle. Lloyd's 2025 Market Oversight Plan reportedly lists delegated-claims data timeliness and accuracy. | **T4 competitor content marketing**, used only for leads to verify. The "Market Oversight Plan" claim was **not** independently verified. |
| B5.11 | OneSchema pricing page | 2026-09-24 | oneschema.co/pricing | Adjacent category (embeddable CSV/Excel importer): Studio Free / $20 per month / $200 per user per month; credits at $0.012; importer tiers "up to 1M / 10M row spreadsheets", "50+ included data types", self-hosting on Enterprise. | Adjacent, not insurance-specific. |
| B5.12 | Flatfile pricing page | 2026-09-24 | flatfile.com/pricing | No public prices ("Talk to sales"). Rebranding noted as "Obvious". | — |
| B5.13 | Duco product pages / press | 2026-09-24 | du.co/product/reconciliation/ ; du.co/duco-launches-reconciliation-for-unstructured-data/ | No-code cloud reconciliation. Unstructured-data reconciliation launched 8 Jul 2024. | Financial markets focus. |
| B5.14 | Cytora homepage; Applied Systems acquisition post | 2026-09-24 | cytora.com; appliedsystems.com/…/cytora-acquisition… | LLM-based "risk digitization" of submissions and claims intake. Acquired by Applied Systems. | Marketing. |
| B5.15 | Artificial Labs blog, "Rapid Bordereaux Extraction" | search result only | artificial.io/company/blog/rapid-bordereaux-extraction… | Artificial has a bordereaux extraction tool. | **Not fetched.** Existence only. |
| B5.16 | Xceedance bordereaux management; Openkoda; TxMinds; V7 Go | search results only | — | Additional entrants in bordereaux ingestion / DA oversight. | **Not fetched.** Existence only. |

### B6. AI/agent engineering and design practice

| # | Source | Type / Tier | Date | URL | Claim supported | Limitation |
|---|---|---|---|---|---|---|
| B6.1 | Claude Code docs, "Best practices for Claude Code" | Vendor docs, T2 | fetched 2026-09-24 | code.claude.com/docs/en/best-practices | "Give Claude a way to verify its work"; explore → plan → implement → commit; keep CLAUDE.md short; a **fresh-context adversarial review** subagent; "If you can't verify it, don't ship it"; "have Claude show evidence rather than asserting success". | Vendor guidance, not experimental evidence. |
| B6.2 | Anthropic Engineering, "Effective context engineering for AI agents" | Vendor, T2 | 2025 | anthropic.com/engineering/effective-context-engineering-for-ai-agents | Minimal prompt first; add instructions from observed failure modes; just-in-time retrieval. | Search snippet plus title; not deeply fetched. |
| B6.3 | Scale Labs SWE-Bench Pro leaderboard | Vendor, T2 | 2026 | labs.scale.com/leaderboard/swe_bench_pro | Contamination-mitigation design (copyleft public and held-out splits, private commercial split). | Leaderboard. |
| B6.4 | Morph, "SWE-bench Pro Leaderboard (September 2026)" | Blog, T4 | Sep 2026 | morphllm.com/swe-bench-pro | Reports a Datacurve audit and a mini-swe-agent issue: agents read the gold patch from `.git` history in SWE-bench Pro containers (a reward-hacking vector). | **T4; third-party claims, not verified with Scale.** Illustrative only. |
| B6.5 | Salesforce Lightning Design System principles (via principles.design mirror and a Salesforce UX Medium post) | T2/T4 | — | principles.design/examples/salesforce-lightning-design-principles | Clarity, Efficiency, Consistency, Beauty. | The official SLDS URL returned 404, so a mirror was used. |
| B6.6 | Microsoft Fluent 2, "Design principles" | T2 | fetched | fluent2.microsoft.design/design-principles | Natural on every platform; Built for focus; One for all, all for one; Unmistakably Microsoft. | — |
| B6.7 | Apple HIG, "Design principles" | T2 | fetched (snippet) | developer.apple.com/design/human-interface-guidelines/design-principles | Familiarity/consistency; simplicity/"establish hierarchy"; consistent feedback keeps people "informed and in control". | — |
| B6.8 | Linear, "The Linear Method – Introduction" | T2 | fetched | linear.app/method/introduction | "Purpose-built"; "Aim for clarity" (don't invent terms); "Say no to busy work"; "Simple first, then powerful". | Product-management method, not a visual system. |
| B6.9 | Stripe, Revolut, Higgsfield design approach | — | — | — | **No primary design-system documentation was retrieved for these three.** Any statements about them in the revalidation are labelled as observation or opinion, not sourced fact. | — |

### B7. Pricing inputs used in unit economics

| # | Source | Type / Tier | Date | Claim |
|---|---|---|---|---|
| B7.1 | Anthropic model pricing table (bundled `claude-api` skill, cached 2026-06-24) | Vendor, T2 | 2026-06-24 | Claude Haiku 4.5 $1 / $5 per MTok in/out; Claude Sonnet 5 $2 / $10; Claude Opus 5.5 $4 / $20. Batch API about 50% off. |

---

## C. First-party empirical evidence produced in this investigation

These are measurements and probes run against the actual repository at
`eee00cf` during this session. They are *evidence*, not literature. Scripts
live in the session scratchpad and are reproduced or summarised in
`TRUEBIND_PRODUCT_REVALIDATION.md` §§3–5 and Appendix A so they can be re-run.

| # | Evidence | Where reported |
|---|---|---|
| C1 | Test-suite runs (bordereaux pytest plus script suites; backend pytest on a fresh checkout vs after `alembic upgrade head`; frontend `tsc` and `eslint`) | REVALIDATION §3 |
| C2 | 18 ingestion/validation correctness probes (P1–P18) plus follow-ups F1–F2 | REVALIDATION §3–4, Appendix A |
| C3 | HTTP benchmark matrix (uvicorn, SQLite and Postgres 16, 1k–250k rows, sheet/column/exception/duplicate/structure variants) | REVALIDATION §5 |
| C4 | Hostile-input security probes S1–S10 | REVALIDATION §19 |
