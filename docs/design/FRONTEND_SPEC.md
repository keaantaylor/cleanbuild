# TrueBind — full front-end rebuild

**Design source:** `TrueBind UI mockups 1.pdf` (the landing page you designed). Everything below extends that design language to the whole product: the marketing site, the sample report and every app screen.
**Replaces:** `TrueBind_Frontend_Prompt_01_Design_System.md`. Don't use that file.

---

## Part A — How to run this (for you, not Claude Code)

1. **Put the references in the repo.** Create `docs/design/` and copy in:
   - `TrueBind UI mockups 1.pdf` → rename to `docs/design/landing-mockup.pdf`
   - this file → `docs/design/FRONTEND_SPEC.md` (Part B is the spec Claude Code reads; Part C is the set of prompts you paste)
   - commit: `git add docs/design && git commit -m "Add front-end design spec"`
2. **Run the sessions in order**, one per fresh Claude Code session (`/clear` between them). Each prompt in Part C is short because it points Claude Code at the relevant sections of the spec. That keeps each session cheap.
3. **Review after each session** using the screenshots it saves to `docs/design/review/`. Only move on when you're happy. If something looks off, run a small follow-up in the same session ("the hero heading is too small — match the PDF"). Don't restart it.
4. **Model choice:** use the top model for Sessions 0, 1 and 4, where design judgement matters most. A lighter model is fine for Sessions 2, 3, 5 and 6, which are mostly applying the system.

| Session | Builds | Rough size |
|---|---|---|
| 0 | Foundations: tokens, fonts, primitives, both shells, `/design-system` | Large |
| 1 | Marketing site: landing page (the mockup, plus more sections), Health Check, sample report | Large |
| 2 | Sign-in, Home, Submissions, Upload + processing | Medium |
| 3 | Mapping review | Medium |
| 4 | Report page, finding drawer, reconciliation, evidence tab | Large |
| 5 | Findings queue, duplicate comparison, notifications | Medium |
| 6 | Evidence, Settings, Binders, error pages, mobile + accessibility pass, final screenshots | Medium |

---

## Part B — FRONTEND_SPEC (Claude Code reads this)

### §1 Principles and honesty rules

1. **The mockup is the source of truth** for look and feel. Match its spacing, type scale, restraint and dark palette on marketing pages. Where this spec and the PDF disagree on visuals, the PDF wins. Where they disagree on copy or claims, this spec wins (see rule 6).
2. **Show real product, not illustration.** Visuals are built in HTML/CSS from realistic bordereau data (spreadsheets, finding rows, audit entries). Don't use stock images, 3D blobs, abstract gradients or icon-circle cards.
3. **Hierarchy comes from type and space, not colour.** Colour carries meaning: status, highlights and the one brand accent.
4. **One primary action per view.**
5. **Plain English.** System codes (`BND_OVER_AUTHORITY`, `CR0035M`) appear small, in mono, *under* a plain label, never instead of one.
6. **Only claim what the product does.** No invented customers, logos, testimonials, "trusted by", percentages or time-saved figures. Sample data is always labelled "Sample". These claims stay behind a `claims` flag in `lib/flags.ts` until the backend fix listed ships:
   - "Every source row is accounted for" → needs backend fix D2 (subtotal rows)
   - "Unmapped and unassessed data is reported, not hidden" → needs D1 (verdict)
   - "EU-hosted" / "Backed up daily" → needs production hosting
   - Sanctions screening, sender portal, scorecard, automations, billing: never mentioned on the marketing site for now.

### §2 Colour tokens

Two themes share one token set. **Marketing pages use `dark`. The app uses `light` by default**, and dark is available later via `data-theme="dark"` on `<html>`. Define both in `styles/tokens.css`. No hex values anywhere else. Keep `lib/colorContrast.ts` and add every text/background pair. All must pass WCAG AA.

```css
:root, [data-theme="light"] {
  --bg: #FFFFFF;            --bg-subtle: #F8F8FB;     --bg-muted: #F1F1F5;
  --surface: #FFFFFF;       --surface-raised: #FFFFFF;
  --border: #E8E8EE;        --border-strong: #D5D6DF;
  --text: #12131E;          --text-2: #5A5C6B;        --text-3: #8A8C99;
  --brand: #2446E0;         --brand-hover: #1C38B8;   --brand-subtle: #EDF0FE;
  --highlight: #5B4FD6;     /* eyebrow labels, timeline dots (light-theme lavender) */
  --band: #262A60;          /* deep indigo feature band */
  --danger: #C8322B;  --danger-bg: #FDEEED;
  --warning: #A35A00; --warning-bg: #FFF4DE;  --cell-warn: #FFECC1;  /* spreadsheet highlight */
  --success: #16804D; --success-bg: #E7F6EE;  --cell-ok: #E9F6EB;
  --neutral: #55576A; --neutral-bg: #F0F0F4;
  --focus: 0 0 0 3px rgba(36,70,224,.25);
  --shadow-float: 0 1px 2px rgba(18,19,30,.05), 0 12px 32px rgba(18,19,30,.10);
}
[data-theme="dark"] {
  --bg: #12131E;            --bg-subtle: #161724;     --bg-muted: #1C1D2A;
  --surface: #171826;       --surface-raised: #1D1E2C;
  --border: #2A2B38;        --border-strong: #383A49;
  --text: #E9E9ED;          --text-2: #AEB1B8;        --text-3: #7A7D8D;
  --brand: #2446E0;         --brand-hover: #3A5BF0;   --brand-subtle: rgba(36,70,224,.14);
  --highlight: #B5ABFC;     /* lavender: eyebrows, timeline dots, loop arrow */
  --band: #262A60;
  --danger: #F47B74;  --danger-bg: rgba(244,123,116,.12);
  --warning: #F2C06B; --warning-bg: rgba(242,192,107,.12);
  --success: #6DC88F; --success-bg: rgba(109,200,143,.12);
  --neutral: #AEB1B8; --neutral-bg: rgba(174,177,184,.10);
  --shadow-float: 0 1px 2px rgba(0,0,0,.3), 0 16px 40px rgba(0,0,0,.45);
}
```
The mockup's light spreadsheet cards on the dark page keep light-theme colours (`--cell-ok`, `--cell-warn`, white table bodies). Render them inside a `data-theme="light"` wrapper.

### §3 Typography, spacing, shape, motion

- **Fonts:** Inter (UI and headings) and JetBrains Mono (codes, cell values, hashes), via `next/font` in `app/fonts.ts`.
- **Scale:** 12 / 13 / 14 (body) / 16 / 20 / 24 / 32 / 44 / 56 / 64px.
  - Marketing H1: 56–64px desktop, 40px mobile, weight 500, tracking −0.03em, line-height 1.05. It sits in a narrow column that breaks over 4 lines as in the mockup.
  - Section H2: 32–40px, weight 500, −0.02em.
  - App H1: 24px, weight 600.
- **Eyebrows:** 11–12px, weight 600, letter-spacing 0.12em, uppercase, `--highlight`. This is the one place uppercase is allowed.
- **Numbers:** always `font-variant-numeric: tabular-nums`, right-aligned in tables.
- **Spacing:** 4px grid (4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 96, 128).
  - Marketing sections: 128px vertical padding desktop, 72px mobile.
  - Marketing content: max-width 1200px. App content: max-width 1280px.
- **Shape:** radius 6 (chips inside tables), 8 (buttons, inputs), 12 (cards, panels), 16 (large marketing visuals). Hairline 1px borders.
- **Shadows:** only on floating layers and marketing product visuals.
- **Motion:** 140ms `cubic-bezier(.2,0,0,1)` for UI; 400–600ms for marketing reveals (fade + 8px rise, once, on scroll into view). Everything respects `prefers-reduced-motion`. Nothing loops except the pipeline auto-advance (§5.3), which pauses on hover.

### §4 Components (`components/ds/*`, CSS Modules)

Keep the stack: Next.js 16, React 19, CSS Modules. Allowed new dependencies: `lucide-react` (icons, 1.5px stroke) and `@radix-ui/react-{dialog,dropdown-menu,popover,tooltip,tabs,select,checkbox,toast}` (unstyled, accessible primitives, styled with our tokens). No Tailwind, no UI kits.

| Component | Spec |
|---|---|
| `Button` | Variants: primary (`--brand` fill, white text), secondary (1px `--border-strong`, transparent), ghost, danger. Marketing uses the mockup's outline style: 1px `--border-strong`, 8px radius, 40px height. Sizes 28/32/36/40. Loading keeps the width. |
| `Chip` / `StatusPill` | 22px, 6px dot + label, 12px/600. Every status goes through `statusMeta()`: FAIL→Breach/danger, REVIEW→Review/warning, PASS→Passed/success, NOT_ASSESSED·NOT_EVALUABLE→Not assessed/neutral, PARTIAL→Partly assessed/neutral, MAPPED_BY_ALIAS→Matched/success, MAPPED_BY_AI→Suggested/warning, UNMAPPED→Unmapped/neutral. |
| `DataTable` | Sticky 36px header, 44px rows, hairline row borders, hover `--bg-subtle`. Column types: text, numeric (right, tabular), code (mono, `--text-2`), two-line (label over mono code), status. Sortable headers, row selection with checkboxes, keyboard row navigation (↑↓, Enter opens), loading skeleton, empty state, sticky first column on mobile. |
| `SheetGrid` | A mini spreadsheet as in the mockup: column letters, row numbers, sheet tabs at the bottom, cells that can be highlighted `warn` / `error` / `ok` with a tooltip explaining the finding. Used on marketing, in the finding drawer and in the mapping preview. Values in mono. |
| `VerdictStrip` | Bordered container split by hairlines. The first column (wider) holds a state chip, title and one sentence. The others hold label + big number + caption. States: CLEAN, ISSUES_OPEN, INCOMPLETE, PROCESSING, FAILED. **When INCOMPLETE, no grade is shown**; show "Grade withheld" with the reasons instead. |
| `CoverageBar` | The mockup's stacked bar: checked (success), flagged (warning), unmapped (neutral hatch), not assessed (neutral). Legend with 4 big numbers underneath. |
| `Stepper` | The mockup's pipeline: 00 Received · 01 Ingest · 02 Map · 03 Validate · 04 Reconcile · 05 Audit. States: done, active (filled pill), upcoming. Used on marketing, the upload/processing screen and the report header. |
| `Timeline` | The vertical/horizontal line with lavender dots and numbered steps (mockup "One audited path"). |
| `EvidenceCard` | Small dark or light card listing evidence lines with a status dot, e.g. "row 5 · incurred 39,171.00 ≠ 37,671.00". |
| `AuditEntry` | `#113 · mapping v3 confirmed by molly · 14:02` plus a hash snippet in mono, and a chain-intact indicator. |
| `Panel`, `PageHeader`, `Tabs`, `Input`, `Select`, `SearchCommand` (⌘K), `Drawer` (right, 560px), `Modal`, `Toast` (bottom-right, never over primary actions), `EmptyState` (left-aligned text + one action), `Skeleton`, `Tooltip`, `Avatar`, `Kbd`, `FileChip` (file-type icon + name + sender) | Standard, using the tokens. |

Delete `HealthRing`, `MetricCard` grids and `Sparkbars` once no screen uses them.

### §5 Marketing site (`app/(marketing)`, dark theme)

Build the landing page to match the PDF, section by section, and add the extra sections marked **NEW**. All visuals are real components (`SheetGrid`, `Stepper`, `EvidenceCard`), not images.

**5.1 Nav** (sticky; transparent at top, then `--bg` at 85% with a 12px backdrop blur and a bottom hairline after 24px of scroll): logo · Why · How it works · Product · Health Check | Sign in · **Book a demo** (outline pill, as in the mockup). On mobile, the links go into a full-height sheet.

**5.2 Hero.**
- Left column: eyebrow "Claims bordereaux integrity"; H1 "Clean claims data. Before it becomes a problem."; the subcopy from the PDF; CTAs "Run a Bordereau Health Check" (primary outline) and "See TrueBind in action" (ghost, scrolls to Product); then two small reassurance lines under a hairline, exactly as in the PDF.
- Right/below: the tilted spreadsheet visual `Harbour_MGA_Claims_Aug26_FINAL_v3.xlsx`, rotated about −8° in perspective, Excel-green title bar, sheet tabs Claims / Reserves / Movements.
- **Detail to add:** after load, a soft scan line passes over the sheet once. Three problem cells then highlight in sequence (incurred mismatch in red, missing loss date in amber, a duplicate row), each with a small callout tag. It's static with reduced motion.

**5.3 Pipeline strip.**
- "RECEIVED — A TPA bordereau as it actually arrives. Three sheets, 1,284 rows, nobody's schema." with the `Stepper`.
- **Detail to add:** the stepper is interactive. Each step swaps a panel below it with a 2–3 line explanation and a mini visual:
  - Received: file chips
  - Ingest: "header found at row 4 · 2 note rows excluded"
  - Map: three header → field rows
  - Validate: three finding lines
  - Reconcile: row-accounting mini waterfall
  - Audit: two hash-chained entries
- It auto-advances every 5s, pauses on hover or focus, and can be operated from the keyboard.

**5.4 The problem.**
- Eyebrow "The problem"; H2 "Every sender has a format. Every format has its own mistakes."
- Three light sheet cards with the exact data from the PDF:
  - Harbour MGA: incurred mismatch and missing loss date
  - Kestrel TPA: same row twice, amber
  - Norland Claims: three date formats
- Each card has its caption below.
- Then the loop row: Excel → E-mail → Manual review → Carrier query → Rework, followed by "↺ and back to the sender" in lavender.
- Closing line in `--text-2`.

**5.5 The solution.**
- Eyebrow "TrueBind"; H2 "The same files. One audited path."; subcopy.
- Sender file chips, then the horizontal `Timeline` with 01 Map / 02 Validate / 03 Reconcile / 04 Audit.
- Each step has the PDF copy and its `EvidenceCard` with the exact lines from the PDF.

**5.6 NEW · Principles** ("What you can hold us to").
- Three columns with no icons, just a 32px mono numeral, a title and two lines each:
  1. **Nothing hidden behind a score.** Every report shows what was checked, what wasn't and why, before any grade.
  2. **Source values are never rewritten.** Findings point at the original cell. Corrections go back to the sender, not into your data.
  3. **Every row accounted for.** Each source row is a claim or a recorded exclusion with its reason (behind the `claims` flag, §1.6).

**5.7 Product** ("The application, not an illustration of it.").
- Left: a vertical list of modules that act as tabs: Intake, Findings, Report, Duplicates, Evidence, Audit trail. Drop "Automations" and "Work queue" from the PDF list; they're merged or hidden in the new app.
- Right: a framed screenshot of the matching **rebuilt** app screen, 16px radius, float shadow, crossfading.
- Caption "Current TrueBind build, captured <month year>". Screenshots are regenerated by Session 6 into `public/product/*.png`.
- "Open the product →" button goes to `/login`.

**5.8 NEW · Who it's for.** Four columns, each with the role, the moment they reach for TrueBind, and what they get:
- **DA analyst:** "a coverholder file lands" → a findings list with row-level evidence and a query list for the sender
- **Head of claims / COO:** "month-end sign-off" → one page showing what was checked and what wasn't
- **Binder / oversight manager:** "quarterly audit" → breaches against the binder terms you enter (label "Beta")
- **Auditor:** "evidence request" → the audit pack

**5.9 NEW · The evidence pack.**
- Left: the copy "One click. Everything an auditor asks for."
- Right: a file-tree visual of `A1_binder_breaches_audit_pack.zip` →
  - `original/A1_binder_breaches.xlsx`
  - `mapping.json`
  - `findings.csv`
  - `exceptions.csv`
  - `decisions.csv`
  - `audit_trail.jsonl`
  - `MANIFEST.sha256`
- The manifest line shows a truncated hash and "verified".

**5.10 NEW · Security and data handling.**
- A two-column list of plain statements: tenant isolation, role-based access, CSV-injection-safe exports, "AI sees headers and masked patterns, never values", files kept for as long as your retention setting.
- Statements that need production hosting sit behind the `claims` flag: "EU-hosted", "encrypted at rest", "daily backups".
- Link to `/security`: a simple page with the same list expanded.

**5.11 Health Check band** (the `--band` indigo section from the PDF): eyebrow, H2 "Send one bordereau. Get back a report you can forward.", the copy, CTAs, `CoverageBar` with 1,259 / 23 / 1 / 2, and "Sample: Harbour MGA · Claims Aug-26 · 1,284 rows · 3m 12s".

**5.12 NEW · FAQ.** An accordion with 6 questions:
- What file types do you read?
- Do you change our data?
- Which standard do you map to?
- What happens to columns you can't map?
- How long does a check take?
- What does a pilot involve?

Answers are 2–3 lines each and follow §1.6.

**5.13 Footer** as in the PDF: logo · Security · Lloyd's CRS v5.2 · Privacy · © 2026 TrueBind.

**5.14 Other marketing pages**
- `/health-check`: a two-column page. Left: what you get (the report contents) and how it works (3 steps: send securely → we run the check → you get the report + evidence pack). Right: a form with name, work email, company, role, "roughly how many bordereaux a month" and a message. Submitting it posts to the existing inbound or email endpoint if configured. Otherwise it shows a "mailto:" fallback. There's no file upload on the public page.
- `/sample-report`: a public, read-only render of the real Report screen (§7.6), driven by a static fixture JSON (`public/sample/report.json`, built from the A1/Harbour sample). A "Sample data" banner sits at the top. This is what "See a sample report →" opens, and the best demo asset.
- `/security` and `/privacy`: simple long-form pages in the marketing shell.
- `Book a demo` opens `mailto:` or a calendar link from `NEXT_PUBLIC_DEMO_URL`.

### §6 App information architecture and shell (`app/(dashboard)`, light theme)

**Navigation (sidebar, 232px, `--bg-subtle`):**
- Logo + org switcher (name + role)
- Home `/overview`
- Submissions `/reports` (also active on `/upload`, `/reports/*`)
- Findings `/exceptions` (open-count badge)
- Evidence `/exports` (also active on `/audit`)
- Binders `/settings?tab=binders` (flag `binders`, "Beta" chip)
- Bottom: Settings and the user menu (profile, security/MFA, sign out)

**Hidden via `lib/flags.ts`** (routes kept, nav removed, direct visits show a friendly "Not available yet" page): inbox, work queue (merged into Home), duplicates (a tab inside Findings), scorecard, automations, alerts page (the bell panel replaces it), todo, sanctions settings, billing, SSO, sender portal.

**Top bar (56px):** breadcrumbs · ⌘K search (submissions, claims by reference, findings, pages) · notifications bell · **New submission** (primary). Remove "Processing online" and the duplicate "New intake" controls.

**Notifications panel** (popover from the bell): grouped per submission ("A1_binder_breaches.xlsx · 2 breaches · 3 min ago"), with Mark all read. The count caps at 9+. It replaces the 98-item alerts page.

### §7 App screens

Each screen gets loading (skeleton), empty, error and permission-denied states. Viewer role: write actions are hidden, not just disabled.

**7.1 Sign in / invite / MFA.**
- Split layout: left is the dark marketing panel with the mockup's pipeline `Stepper` and one line of copy; right is the light form.
- Fields: email, password, "Continue". The MFA step is a 6-digit code input with auto-advance. Accepting an invite shows the org name and role being joined.
- Errors appear inline under the field, in plain English.

**7.2 Home — "What needs a decision"**
- Header: "Good morning, Kealan" plus the date. Actions: New submission.
- A row of 4 counters in a single `VerdictStrip`-style container:
  - **Breaches open**
  - **Findings to review**
  - **Submissions incomplete**, meaning grade withheld
  - **Due this week**, meaning obligations
- **Needs a decision:** a `DataTable` of the top 10 open findings across all submissions, most severe first. Columns: status · finding (label + code) · submission · claim · amount · age · owner.
- **Recent submissions:** 5 rows with verdict chips.
- A right rail (320px) with **Deadlines** (obligations) and **Activity** (last 8 audit entries).
- Empty state for a new org: a 3-step checklist (Upload your first bordereau → Confirm the mapping → Review findings) plus a "Try the sample file" button that loads a bundled fixture.

**7.3 Submissions list**
- Filters: sender, status, verdict, date range, and a search box. Saved views appear as tabs: All · Needs review · Incomplete · Clean.
- Table columns: file (FileChip) · sender · programme · received · rows · verdict chip · open findings (breach/review counts) · owner.
- Bulk actions: export and assign. Clicking a row opens the report.

**7.4 Upload + processing**
- Step 1: a large dropzone (xlsx, xlsm, xls, csv, up to the configured limit) with sender and programme selects and an optional reporting period.
- Step 2: the processing view uses the `Stepper` with live states (Received → Ingest → Map…). Under it is a live log in mono ("Sheet 'Claims' · header found at row 4 · 1,204 rows"), and time elapsed.
- On failure, show the plain reason plus the sheet, column and row when known, with Retry and Upload a new file. Never show "Processing failed unexpectedly" alone.
- When mapping needs confirmation, go straight to 7.5.

**7.5 Mapping review**
- Sheet tabs along the top, each showing its type (Claims · Premium · Summary · Unknown) and status. Non-claim sheets show "Skipped — looks like a premium bordereau" with an "Include anyway" link.
- The main table is one row per source column:
  - source header (mono)
  - 3 sample values, masked where the backend masks them
  - arrow → canonical field (a `Select`, searchable, grouped by CRS section)
  - method chip: Matched / Suggested / Unmapped
  - required marker
- A right panel (340px) holds the **Required fields checklist**: each CRS required field with a ✓ or "Not mapped". It also shows a preview `SheetGrid` of the first 5 rows as mapped.
- Footer bar (sticky):
  - Primary "Confirm mapping" when all required fields are mapped.
  - Otherwise the primary becomes "Review 4 missing fields" (it scrolls to them), and a secondary "Process anyway — grade withheld" opens a confirmation modal that explains the consequence. This matches backend fix D7.
- **The toast must never cover this bar.**

**7.6 Report** (the flagship screen; also used by `/sample-report`)
- Header: breadcrumb, file name (H1), sender · programme · received · rows, then actions: Export ▾ (claims CSV, findings CSV), Audit pack, and the primary action, which depends on the verdict ("Review breaches" / "Review findings" / "Accept bordereau").
- `VerdictStrip`:
  - State column, e.g. "2 breaches open — Not ready to accept", with one sentence underneath.
  - Claims assessed "4 / 4", with "every source row reconciles" or "2 rows excluded (subtotal) — see Reconciliation".
  - Total incurred, per currency. Multiple currencies are listed, never summed.
  - Data quality: grade, "capped while breaches are open", or "withheld" with reasons.
- `Stepper` in compact form, showing which checks ran. Hovering a step shows what was run and not run.
- Tabs:
  - **Findings (n):** a `DataTable` grouped by severity (Breach, Review, Not assessed). Row click opens the **finding drawer** (7.7). Filters: check (Data, Arithmetic, Binder, Payments, Duplicates), status and sheet.
  - **Claims (n):** a table of canonical claims with a findings count per claim, searchable by reference.
  - **Mapping:** a read-only view of the confirmed mapping, plus who confirmed it and when.
  - **Reconciliation:** the row-accounting waterfall (source rows → excluded by reason → claims → assessed), with expandable excluded rows showing the original values. This is where "every row accounted for" is proven.
  - **Evidence:** audit entries for this report (`AuditEntry` list), a chain-verification button showing "Chain intact · 116 entries", and the audit pack download with its manifest listing.
- **Processing / failed states** use the same header, with the Stepper and a reason panel in place of the tabs.

**7.7 Finding drawer** (right, 560px)
- Title: plain label plus a status chip, with the rule code in mono underneath.
- A "Where" line: sheet · row · field, followed by a `SheetGrid` excerpt of the source row and its neighbours, with the offending cell highlighted.
- A "Why" block: an explanation in one or two sentences, with the numbers (e.g. "Incurred 75,000.00 exceeds the £50,000 settlement authority by £25,000.00").
- **Decision** buttons:
  - Accept as valid (needs a reason)
  - Query sender (adds the finding to the sender query list)
  - Dismiss (needs a reason)
- Assign owner, a comments thread and a history of decisions, all taken from the audit log.
- Keyboard: J/K for next and previous finding, Esc to close.

**7.8 Findings queue** (`/exceptions`)
- Every open finding across submissions: saved views (My queue · Breaches · Needs review · Not assessed · Decided), filters, bulk assign and bulk decision (with a reason).
- **Duplicates** is a tab here. Its comparison view shows the two rows side by side as `SheetGrid`s with the differing cells highlighted, and a "Same claim, later period (development)" vs "Exact resubmission" explanation. Decisions work as in 7.7.
- **Sender query list:** a tab collecting all "Query sender" findings per sender. Export it as CSV, or copy it as a formatted email body.

**7.9 Evidence** (`/exports`, `/audit`)
- Two tabs.
  - **Audit trail:** paginated at 50 per page, with filters (actor, action, submission, date). A "Verify chain" button shows a result banner. Entries use `AuditEntry`.
  - **Exports & packs:** a history of generated files with who, when, size and a download link.
- No page is allowed to grow unbounded again (the old audit page was 23,000px).

**7.10 Settings** (tabs)
- Organisation: name, retention period, time zone.
- Members: table, invite, role change and remove, with the role explained in plain words.
- Security: MFA for yourself, and an org-wide MFA requirement toggle for admins.
- Channels: email inbound address and SFTP, each shown with an honest state ("Available — needs setup" / "Active").
- Binders: flagged Beta.
- Hidden (§6): SSO, billing, sanctions, webhooks unless configured.

**7.11 Binders (Beta)**
- List: name, coverholder, period, currency, authority, attachment basis.
- Create/edit form fields:
  - name, coverholder, UMR (optional)
  - inception and expiry dates
  - **attachment basis** (risks attaching / losses occurring), with helper text
  - permitted currencies (multi-select)
  - per-claim settlement authority and currency
- A banner reads: "Binder checks are in beta. Confirm results against the binding authority wording before issuing any breach notice."

**7.12 System pages:** 404, 403 ("You don't have access to this — ask an admin"), 500 with a reference ID, "Not available yet" for hidden modules, and maintenance. They use the light app shell, or the marketing shell when signed out.

### §8 Vocabulary

| Old | New |
|---|---|
| Reports / Intake / Inbox | Submissions |
| New intake | New submission |
| Exceptions / module findings | Findings |
| Exports / Audit trail | Evidence |
| Overview / Work queue | Home |
| NOT_EVALUABLE / not assessed / not configured | Not assessed (for checks) · Available — needs setup (for channels) |
| Excellent / Good / Fair / Poor / Very poor | Grade 5–1, shown only with its coverage; never alone as the headline |
| Open exposure | Amounts flagged for review |
| Processing online / Engine online | *(remove)* |

Microcopy style:
- Sentence case, no exclamation marks.
- Numbers with thousands separators; currency always with its code or symbol.
- Relative time with the absolute time on hover.
- Error messages say what happened, where, and what to do next.

### §9 Data adapters (temporary, until the backend fixes land)

The backend fixes from the technical analysis (D1 verdict, D10 unified findings) may not exist yet. Build the UI against these interfaces in a new `lib/verdict.ts` and in the existing `lib/findings.ts` (extend it; keep its current exports working):
```ts
type VerdictState = "CLEAN" | "ISSUES_OPEN" | "INCOMPLETE" | "PROCESSING" | "FAILED";
interface Verdict { state: VerdictState; grade: number | null; reasons: string[];
  counts: { breaches: number; review: number; notAssessed: number } }
interface UnifiedFinding { id: string; reportId: string; source: "engine" | "module";
  rule: string; label: string; status: "FAIL"|"REVIEW"|"PASS"|"NOT_ASSESSED";
  state: "OPEN"|"DECIDED"; sheet?: string; row?: number; field?: string;
  claimRef?: string; amount?: { value: number; currency: string }; message: string }
```
- `getVerdict(reportId)` calls `GET /api/v1/reports/{id}/verdict` if that endpoint exists (feature-detect the 404). Otherwise it derives a verdict from `getReportSummary` + `listModuleFindings`, using the D1 rules:
  - any unmapped required field or unmapped money columns → INCOMPLETE, no grade
  - any open FAIL → ISSUES_OPEN, grade capped at 3
  - otherwise CLEAN
- `listFindings()` unions `listExceptions` and `listModuleFindings` the same way.

Mark both fallbacks `// TEMPORARY — remove when backend D1/D10 ship`. The screens must never compute a verdict themselves. They only call these functions.

### §10 Responsive and accessibility

- Breakpoints: 390 · 768 · 1024 · 1280 · 1440.
  - Below 1024: the sidebar becomes a drawer and right rails stack under the content.
  - Below 768: tables become stacked cards showing the 3 key columns, with a "details" expander.
- **No horizontal page scroll at 390px**, checked by a test.
- Keyboard: everything is reachable; focus rings are visible (`--focus`); drawers and modals trap focus and return it on close; ⌘K is global.
- Semantics: landmarks, `aria-live` for processing status, tables with proper headers, chips with text, not colour alone.

### §11 QA and acceptance (used by every session)

1. `npm run lint && npm run build && npm run test` passes in `truebind-web/frontend`.
2. `tests/visual/<session>.spec.ts` saves screenshots at 1440 and 390 into `docs/design/review/<session>/`, and asserts `scrollWidth <= 390` on mobile.
3. The contrast check passes for every new token pair.
4. No hex values outside `styles/tokens.css` (grep `*.module.css`).
5. No raw status codes visible in the UI (grep the rendered pages for `NOT_EVALUABLE|BND_|LKG_|CR0` outside mono sub-labels).
6. Existing tests keep their meaning. Update labels, but never weaken an assertion.

---

## Part C — Session prompts (paste one per fresh Claude Code session)

Every prompt starts with the same header. It's included in each block so you can paste them one at a time.

### Session 0 — Foundations

=== PASTE FROM HERE ===
You are a senior product designer-engineer rebuilding TrueBind's front end to the standard of Linear, Stripe and Revolut Business.
Read `docs/design/FRONTEND_SPEC.md` §1–§4, §6 (shell only), §8, §10 and §11. Open `docs/design/landing-mockup.pdf` to absorb the visual language.
Credit rules:
- Read only the spec sections named and the files listed. Read other files only if a build or type error names them.
- Run the verification once, at the end. If the same error fails twice, stop and report.
- Final reply: files changed, new dependencies, the last 20 lines of test output, and screenshot paths. No file dumps.

Task: build the foundations only. No page redesigns yet.
1. Create `styles/tokens.css` with both themes (§2). Remove the old `variables.css` values (keep the file importing tokens.css until nothing references it). Update `lib/colorContrast.ts`.
2. Set up fonts in `app/fonts.ts` (§3), plus global type and base styles in `styles/globals.css`.
3. Build or restyle every component in §4 in `components/ds`. Keep existing export names compiling so current pages still build. Add `lucide-react` and the listed Radix primitives.
4. Build two shells:
   - `components/layout/MarketingShell` (dark: nav + footer from §5.1 and §5.13)
   - `components/layout/AppShell` (light: sidebar, top bar, ⌘K and notifications popover from §6), with `lib/flags.ts` controlling nav visibility
   - Wire `app/(marketing)/layout.tsx` and `app/(dashboard)/layout.tsx` to them.
5. Create `app/(dashboard)/design-system/page.tsx`, which renders every component, variant and state in both themes. It returns 404 in production.
6. Verify per §11. Screenshots: `/design-system` (light and dark) and `/overview` at 1440 and 390.

Files to read: `styles/*`, `app/fonts.ts`, `app/layout.tsx`, `app/(dashboard)/layout.tsx`, `app/(marketing)/layout.tsx`, `components/ds/*`, `components/ui/*`, `components/layout/*`, `lib/colorContrast.ts`.
=== TO HERE ===

### Session 1 — Marketing site

=== PASTE FROM HERE ===
You are a senior product designer-engineer rebuilding TrueBind's front end to the standard of Linear, Stripe and Revolut Business.
Read `docs/design/FRONTEND_SPEC.md` §1–§3 and §5, and open `docs/design/landing-mockup.pdf`. The design system and shells from Session 0 exist in `components/ds` and `components/layout`. Use them, and read their index files only.
Credit rules:
- Read only the spec sections named and the files listed. Read other files only if a build or type error names them.
- Run the verification once, at the end. If the same error fails twice, stop and report.
- Final reply: files changed, the last 20 lines of test output, and screenshot paths. No file dumps.

Task: rebuild the marketing site.
1. Replace `components/landing/*` with a new landing page matching the PDF section by section (§5.1–§5.5, §5.11, §5.13), plus the NEW sections §5.6–§5.10 and §5.12. Every visual is built from `SheetGrid`, `Stepper`, `Timeline`, `EvidenceCard` and `CoverageBar`, using the exact sample data in the PDF. Delete the old `EngineScene`.
2. Add the interactive pipeline (§5.3) and the one-time hero scan (§5.2), respecting reduced motion.
3. Put claims behind `lib/flags.ts` → `claims` as §1.6 describes.
4. Build `/health-check`, `/sample-report` (static fixture; reuse the Report screen components if they already exist, otherwise build a read-only version with the §7.6 layout), `/security` and `/privacy` (§5.14).
5. Compare your screenshot against the PDF at 1440px, section by section. Fix spacing, type size and colour differences before finishing.
6. Verify per §11. Screenshots: full-page `/` at 1440 and 390, plus `/health-check` and `/sample-report` at 1440.

Files to read: `app/(marketing)/*`, `components/landing/*`, `components/ds/index.tsx`, `components/layout/MarketingShell*`, `lib/flags.ts`.
=== TO HERE ===

### Session 2 — Sign-in, Home, Submissions, Upload

=== PASTE FROM HERE ===
You are a senior product designer-engineer rebuilding TrueBind's front end to the standard of Linear, Stripe and Revolut Business.
Read `docs/design/FRONTEND_SPEC.md` §1, §6, §7.1–§7.4, §8, §9 and §11. Use the existing `components/ds` (read its index only).
Credit rules:
- Read only the spec sections named and the files listed. Read other files only if a build or type error names them.
- Run the verification once, at the end. If the same error fails twice, stop and report.
- Final reply: files changed, the last 20 lines of test output, and screenshot paths. No file dumps.

Task:
1. Create `lib/verdict.ts` and extend the existing `lib/findings.ts` exactly as in §9. Keep its current exports.
2. Rebuild these screens with their loading, empty, error and permission states:
   - `app/login`, `app/invite` (§7.1)
   - `app/(dashboard)/overview` (Home, §7.2)
   - `app/(dashboard)/reports/page.tsx` (Submissions list, §7.3)
   - `app/(dashboard)/upload` + `components/intake/ProcessingView` (§7.4)
3. Keep all API calls through `lib/api.ts`. Don't change backend behaviour.
4. Verify per §11. Screenshots: the 4 screens at 1440 and 390, plus the Home empty state.

Files to read: those route folders, `components/intake/ProcessingView.tsx`, `components/intake/IntakeStepper.tsx`, `lib/api.ts` (function signatures only), `lib/types.ts`.
=== TO HERE ===

### Session 3 — Mapping review

=== PASTE FROM HERE ===
You are a senior product designer-engineer rebuilding TrueBind's front end to the standard of Linear, Stripe and Revolut Business.
Read `docs/design/FRONTEND_SPEC.md` §1, §7.5, §8 and §11. Use the existing `components/ds`.
Credit rules:
- Read only the spec sections named and the files listed. Read other files only if a build or type error names them.
- Run the verification once, at the end. If the same error fails twice, stop and report.
- Final reply: files changed, the last 20 lines of test output, and screenshot paths. No file dumps.

Task: rebuild mapping review per §7.5.
1. Include sheet-type tabs, the column table, the required-fields checklist, the `SheetGrid` preview and the sticky footer with the missing-required guard ("Process anyway — grade withheld" confirmation modal).
2. If the confirm endpoint doesn't yet accept an acknowledgement flag, send the normal confirm after the modal and add a `// TODO backend D7` comment.
3. The processing toast must never overlap the footer bar. Add a Playwright assertion for this.
4. Verify per §11. Screenshots: a fully mapped sheet, a sheet with 4 missing required fields, a skipped premium sheet, and the confirmation modal, at 1440, plus one at 390.

Files to read: `components/intake/MappingReview.tsx`, `components/intake/intake.module.css`, `app/(dashboard)/upload/*`, `lib/api.ts` (mapping functions only), `lib/types.ts`.
=== TO HERE ===

### Session 4 — Report page and finding drawer

=== PASTE FROM HERE ===
You are a senior product designer-engineer rebuilding TrueBind's front end to the standard of Linear, Stripe and Revolut Business.
Read `docs/design/FRONTEND_SPEC.md` §1, §7.6, §7.7, §8, §9 and §11. Use the existing `components/ds`, `lib/verdict.ts` and `lib/findings.ts`.
Credit rules:
- Read only the spec sections named and the files listed. Read other files only if a build or type error names them.
- Run the verification once, at the end. If the same error fails twice, stop and report.
- Final reply: files changed, the last 20 lines of test output, and screenshot paths. No file dumps.

Task: rebuild the Report screen and finding drawer per §7.6 and §7.7. This is the flagship screen.
1. Delete the client-side `executiveSummary()`. All headline text comes from `getVerdict()`.
2. Build the tabs: Findings, Claims, Mapping, Reconciliation (row-accounting waterfall with expandable excluded rows) and Evidence (audit entries, chain verification, audit pack).
3. Build the drawer with the `SheetGrid` source excerpt, the decision actions (via `disposeFinding` / `reviewException`), comments and history, plus J/K navigation.
4. Make `/sample-report` render this same screen from the static fixture.
5. Test the verdict states with fixtures: CLEAN, ISSUES_OPEN (the A1 sample), INCOMPLETE (A2: 4 required fields unmapped, grade withheld), PROCESSING and FAILED.
6. Verify per §11. Screenshots: each verdict state at 1440, the drawer open, the Reconciliation tab, and the report at 390.

Files to read: `app/(dashboard)/reports/[reportId]/*`, `components/report/*`, `components/exceptions/*` (only to reuse logic), `lib/api.ts` (report, exception and module functions), `lib/types.ts`.
=== TO HERE ===

### Session 5 — Findings queue, duplicates, notifications

=== PASTE FROM HERE ===
You are a senior product designer-engineer rebuilding TrueBind's front end to the standard of Linear, Stripe and Revolut Business.
Read `docs/design/FRONTEND_SPEC.md` §1, §6 (notifications), §7.8, §8 and §11. Reuse the finding drawer from Session 4.
Credit rules:
- Read only the spec sections named and the files listed. Read other files only if a build or type error names them.
- Run the verification once, at the end. If the same error fails twice, stop and report.
- Final reply: files changed, the last 20 lines of test output, and screenshot paths. No file dumps.

Task:
1. Rebuild `/exceptions` as the Findings queue with saved views, filters, and bulk assign/decide.
2. Add the Duplicates tab with the side-by-side comparison, and the Sender query list tab (CSV export + copy as email).
3. Build the notifications popover grouped per submission.
4. Hide the old `/duplicates` and `/alerts` pages behind flags with the "Not available yet" page.
5. Currency formatting must go through `formatMoney()` only. Delete `formatCurrency` and add the ESLint restriction on `Intl.NumberFormat` currency usage outside `lib/formatters.ts`. A report containing "$" must render.
6. Verify per §11. Screenshots: the queue, duplicate comparison, sender query list and the notifications popover at 1440, plus the queue at 390.

Files to read: `app/(dashboard)/exceptions/*`, `app/(dashboard)/duplicates/*`, `components/exceptions/*`, `lib/formatters.ts`, `lib/api.ts` (exceptions, duplicates and alerts functions).
=== TO HERE ===

### Session 6 — Evidence, Settings, Binders, polish

=== PASTE FROM HERE ===
You are a senior product designer-engineer rebuilding TrueBind's front end to the standard of Linear, Stripe and Revolut Business.
Read `docs/design/FRONTEND_SPEC.md` §6, §7.9–§7.12, §10 and §11.
Credit rules:
- Read only the spec sections named and the files listed. Read other files only if a build or type error names them.
- Run the verification once, at the end. If the same error fails twice, stop and report.
- Final reply: files changed, the last 20 lines of test output, and screenshot paths. No file dumps.

Task:
1. Rebuild Evidence (paginated audit trail with chain verification, plus the exports history), Settings (the tabs listed; hide SSO, billing and sanctions) and the Binders Beta form with attachment basis.
2. Build the system pages from §7.12.
3. Do an accessibility and mobile pass across all rebuilt screens (§10). Fix any horizontal scroll, focus issues or missing labels.
4. Regenerate the marketing product screenshots into `public/product/*.png` from the rebuilt screens, using the sample fixture data only, and update §5.7's caption date.
5. Delete components no longer used anywhere (`HealthRing`, `MetricCard`, `Sparkbars`, old landing files, unused CSS modules). Run `npx ts-prune` or a grep to confirm they're unused.
6. Final verification per §11 across the whole app. Screenshots of every nav destination at 1440 and 390 go into `docs/design/review/final/`.

Files to read: `app/(dashboard)/exports/*`, `app/(dashboard)/audit/*`, `app/(dashboard)/settings/*`, `components/settings/*`, `app/not-found.tsx`, `app/error.tsx`.
=== TO HERE ===

---

## Part D — Check before you show anyone

- [ ] The landing page matches the PDF side by side at 1440px
- [ ] The A1 sample report says "2 breaches open — Not ready to accept", never "Excellent"
- [ ] The A2 sample shows "Grade withheld — 4 required fields not mapped"
- [ ] No invented customers, logos, testimonials or percentages anywhere
- [ ] Flagged claims (§1.6) stay off until their backend fixes ship
- [ ] Every page works at 390px without sideways scrolling
- [ ] `/sample-report` is the demo link in your outreach emails
