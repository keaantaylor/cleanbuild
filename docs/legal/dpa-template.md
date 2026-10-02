# Data Processing Agreement — DRAFT TEMPLATE

> **Draft for review by a solicitor before use.** Not legal advice. Square-bracketed items must be completed or
> confirmed. Written to match how the TrueBind service actually works (see `/security` and `docs/strategy.md`);
> if the service changes (hosting region, sub-processors), update Annex 3 and the security page together.

**Between**

- **[CUSTOMER LEGAL NAME]**, [address], [company number] (the **Controller**); and
- **[TRUEBIND LEGAL ENTITY]**, trading as TrueBind, [address], [company number] (the **Processor**).

Effective from [DATE]. This agreement forms part of the [Terms of Service / Order Form dated DATE] (the **Main
Agreement**).

## 1. Definitions
Terms such as *personal data*, *processing*, *controller*, *processor*, *data subject* and *personal data breach*
have the meanings in the GDPR (Regulation (EU) 2016/679) and, where it applies, the UK GDPR and Data Protection
Act 2018 (together **Data Protection Law**).

## 2. Subject matter and duration
2.1 The Processor processes personal data contained in files the Controller uploads (bordereaux and related
workbooks) only to provide the TrueBind service described in Annex 1.
2.2 This agreement lasts as long as the Processor processes personal data for the Controller.

## 3. Controller instructions
3.1 The Processor processes personal data only on the Controller's documented instructions, which are this
agreement, the Main Agreement and the Controller's use of the service's settings (including the retention period
and the "Anonymise insured names" option).
3.2 The Processor will tell the Controller promptly if, in its opinion, an instruction infringes Data Protection
Law.

## 4. Processor obligations
4.1 **Confidentiality.** Everyone authorised to process the personal data is bound by confidentiality.
4.2 **Security.** The Processor implements the measures in Annex 2.
4.3 **Sub-processors.** The Controller gives general authorisation for the sub-processors in Annex 3. The
Processor will give at least [30] days' notice by email of any new or replacement sub-processor; the Controller
may object on reasonable grounds within that period, and if the parties cannot resolve the objection the
Controller may terminate the affected service. The Processor imposes data protection obligations on each
sub-processor equivalent to this agreement and remains liable for them.
4.4 **Data subject requests.** Taking into account the nature of the processing, the Processor assists the
Controller in responding to requests from data subjects. Requests received directly are forwarded to the
Controller without undue delay.
4.5 **Breaches.** The Processor notifies the Controller without undue delay, and in any case within [48] hours,
after becoming aware of a personal data breach affecting the Controller's data, with the information the
Controller needs to meet its own obligations.
4.6 **Assistance.** The Processor assists with data protection impact assessments and prior consultation where
required, to the extent the information is available to it.
4.7 **Records and audit.** The Processor makes available the information necessary to demonstrate compliance
and allows for audits by the Controller or its mandated auditor, on [30] days' notice, at most once a year unless
a breach or regulator requires otherwise, at the Controller's cost. The service's hash-chained audit trail and
audit pack are available to the Controller at any time.

## 5. International transfers
5.1 Personal data is processed in the United States (see Annex 3). Where Data Protection Law requires, transfers
are made under the European Commission's Standard Contractual Clauses (Module [3: processor to processor]) and,
for UK data, the UK International Data Transfer Addendum, as incorporated in the relevant sub-processor's terms
[and/or the EU-US Data Privacy Framework where the sub-processor is certified].
5.2 [If the Controller requires EU/UK-only hosting, record the agreed arrangement here.]

## 6. Deletion and return
6.1 Uploaded files, the rows read from them and the findings are permanently deleted at the end of the retention
period the Controller sets in the service (default 30 days, configurable from 1 to 365 days), or immediately when
the Controller deletes a report. Copies in the hosting provider's database backups expire on that provider's
backup schedule ([state period]).
6.2 On termination the Processor deletes all remaining personal data within [30] days, unless law requires
retention. Before then the Controller may export its data from the service.
6.3 The audit trail retains only file names, file fingerprints (SHA-256) and the actions taken, so that the
chain remains verifiable; it does not retain the contents of the files.

## 7. Liability
Each party's liability under this agreement is subject to the limitations in the Main Agreement [except where
Data Protection Law does not allow limitation].

## 8. Governing law
This agreement is governed by the laws of [Ireland] and the courts of [Ireland] have exclusive jurisdiction.

Signed for the Controller: ____________________  Name / role / date: ____________________

Signed for the Processor: ____________________  Name / role / date: ____________________

---

## Annex 1 — Description of the processing

| | |
|---|---|
| Nature and purpose | Reading bordereaux and related workbooks; checking them for errors (required data, arithmetic, dates, currency, status, policy period and limit, duplicates); producing reports, an annotated workbook, a corrected copy, a query letter and month-on-month comparisons for the Controller. |
| Categories of data subjects | Insured parties, claimants and policyholders named in the files; the Controller's staff who use the service. |
| Categories of personal data | Names of insureds/claimants, claim and policy references, loss dates, claim amounts and statuses, and any other content the Controller places in the files; for users: name, work email, role, sign-in records. |
| Special category data | Not intended. The Controller should not upload special category data (for example health details) unless the parties agree additional measures in writing. |
| Frequency | Continuous, for each file uploaded. |
| Retention | As in section 6. |

## Annex 2 — Technical and organisational measures (as built)

- Every upload is fingerprinted (SHA-256) and stored write-once; processing works on a parsed copy and never alters the original.
- Encryption in transit (HTTPS/TLS) for all traffic. [Confirm and state encryption at rest provided by the hosting provider.]
- Each organisation's data is separated in the database by PostgreSQL row-level security; every query runs in the organisation's context.
- Role-based access (Owner, Admin, Analyst, Viewer, Sender); optional or organisation-wide mandatory two-step verification; single sign-on via Microsoft Entra ID or any OpenID Connect provider.
- Hash-chained, append-only audit trail of every action; tampering is detectable by verification.
- Spreadsheet formula injection neutralised in every export; cell text treated as data, never as instructions, including in AI prompts.
- AI-assisted mapping (if enabled) receives only column headers and masked value shapes, from an EU or UK region provider, with zero retention configured; suggestions require human confirmation.
- Optional anonymisation of insured names in everything the service stores.
- Automatic permanent deletion after the configured retention period.
- [Backups: provider, frequency, retention, encryption.]
- [Staff access policy, vetting, training — complete.]
- [Incident response contact and process — complete.]

## Annex 3 — Approved sub-processors

| Sub-processor | Purpose | Location |
|---|---|---|
| Render Services, Inc. | Application and PostgreSQL database hosting | United States (US-East, Virginia) |
| Vercel Inc. | Website hosting and request routing | United States (iad1) [confirm edge regions] |
| [Email provider] | Sending emails the Controller asks the service to send | [location] |
| Stripe, Inc. / Stripe Payments Europe | Billing (only if the Controller subscribes) | [EU/US] |
| [Microsoft Azure OpenAI / Amazon Bedrock] | AI-assisted column mapping, only if enabled | [EU/UK region] |
