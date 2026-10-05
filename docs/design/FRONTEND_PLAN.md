# TrueBind front-end plan

Companion to `FRONTEND_SPEC.md` (written before backend Phases 1–5) and `landing-mockup.pdf`.
This file is the screen inventory, the API each screen uses, which session builds it, and every
gap between spec, PDF and the real backend on branch `rebuild` (b94b1ac). Written 2026-10-05.

Endpoints are given as `lib/api.ts` function → backend path (all under `/api/v1`).

---

## 1. Decisions and conflicts (resolve before or during the session named)

| # | Conflict | Resolution in this plan |
|---|---|---|
| C1 | Spec assumes CSS Modules, lucide and Radix, "no Tailwind". The front end is **Tailwind v4 + Phosphor**. | Decided 2026-10-05: no library switches. New components use CSS Modules (built into Next) and native `<dialog>`; Phosphor stays (the PDF uses it); Tailwind stays for old screens and is removed only if nothing uses it after Session 8. |
| C2 | Spec paths (`components/ds`, `components/ui`, `components/landing`, `components/intake`, `components/report`, `components/exceptions`, `components/settings`, `app/fonts.ts`, `styles/variables.css`) **don't exist**. All UI is in `components/nocturne/*` and `components/site/*`. | Session 0 creates `components/ds`. Each later session moves its screen out of `nocturne/` into a feature folder (`components/report`, …) and deletes the old file when nothing imports it. |
| C3 | Fonts: build self-hosted **IBM Plex**. PDF is set in **Inter**. | Inter restored from git history (the PDF's typeface); IBM Plex Mono kept for codes. Both self-hosted via `app/fonts.ts`. |
| C4 | The PDF hero has a soft radial glow and the Health Check band a faint gradient. | Decided 2026-10-05: the PDF wins on marketing (tokens `--glow-hero`, `--glow-band`, dark theme only). No gradients in the app. |
| C5 | PDF draws "↺ and back to the sender" in **amber**; spec §5.4 says lavender. | Follow the PDF (amber, `--warning`): the PDF wins on visuals (spec §1.1). |
| C6 | PDF/spec copy uses em dashes ("can't place — never cell values"). The rebuild removed em dashes deliberately. | Replace with commas or full stops; wording otherwise unchanged. |
| C7 | PDF hero line "Unmapped and unassessed data is reported, not hidden" is behind the `claims` flag (needs D1, which hasn't shipped). "Matches the PDF exactly" vs "honesty". | Line is built but off by default. Hero shows only the first reassurance line plus "Source values are never rewritten." (true today). Turn on when D1 ships. |
| C8 | Spec §7.7 decisions "Accept as valid / Query sender / Dismiss" via `disposeFinding`/`reviewException`. Phase 1–4 replaced this with an **issue lifecycle** (DETECTED → … → RESOLVED / OVERRIDDEN / AUTO_FIXED), **root-cause bulk decisions** and **corrections under policy**. | Engine findings use the issues API: Accept as reported = `override` (reason required), Query sender = `send_to_sender` (creates a `[TB-n]` request), Resolve, Propose correction. Module (binder/payments) findings keep `disposeFinding`. |
| C9 | Spec Report opens on Findings. Phase 1/5 made the report open on the **review queue** (one root cause at a time) with the **workbook grid** as the review surface. | Report tabs: **Review** (root causes, default when issues are open) · **Workbook** · Findings · Claims · Mapping · Reconciliation · Evidence. Findings table stays for filtering/export. |
| C10 | `/design-system` under `app/(dashboard)` sits behind AuthGate, so it can't render without a live API. | Put it at `app/design-system/page.tsx` (outside AuthGate, wrapped in AppShell with a stub user), `notFound()` in production. |
| C11 | Spec grade is a number 1–5; backend `report.grade` is a word ("Excellent"…) plus `score`. | `lib/verdict.ts` maps word → 5..1 and applies the D1 caps; screens never show the word. |
| C12 | Spec nav has no place for **sender memory** (Phase 4). | Add **Senders** (`/senders`) to the sidebar between Findings and Evidence. |
| C13 | Spec hides the sender portal; SENDER-role users exist and land on `app/sender`. | Keep the route; restyle it lightly in Session 8 with AppShell's sender variant. Never mentioned on the marketing site. |
| C15 | Spec light tokens `--text-3 #8A8C99` (3.4:1 on white) and `--success #16804D` (4.45:1 on its tint) fail AA. | Darkened to `#686A7A` and `#157A4A`; `tests/unit/tokens.test.ts` checks every pair and that `lib/colorContrast.ts` matches `tokens.css`. |
| C16 | ⌘K spec includes claims and findings, but both search endpoints are per report (G3). | Palette covers pages, actions and submissions; findings/claims search waits for a tenant-wide endpoint. |
| C14 | `app/onboarding` (675 lines) isn't in the spec. | Rebuilt in Session 2 as a 3-step checklist inside the Home empty state; the route redirects there. |

---

## 2. Screens

### Marketing (dark, `MarketingShell`): Session 1
| Screen | Route | API | Notes |
|---|---|---|---|
| Landing | `/` | none | §5.1–5.13. Interactive pipeline, one-time hero scan, claims flag. Product screenshots are placeholders until Session 8 regenerates them. |
| Health Check | `/health-check` | `POST /leads/health-check` | Form only, no file upload. On success: "We'll be in touch" (nothing is e-mailed until you name an inbox). |
| Sample report | `/sample-report` | none (static `public/sample/report.json`) | Session 1 builds a read-only layout; Session 4 swaps it for the real Report screen. |
| Security, Privacy | `/security`, `/privacy` | none | Long-form. Hosting claims behind the flag. |
| Existing `/crs`, `/demo`, `/pricing` | | | `/crs` restyled (footer link "Lloyd's CRS v5.2"); `/pricing` hidden by flag; `/demo` → redirect to `NEXT_PUBLIC_DEMO_URL` or mailto. |

### Auth: Session 2
| Screen | Route | API |
|---|---|---|
| Sign in + MFA | `/login` | `login` → `POST /auth/login` (may return MFA challenge), `verifyMfa` → `POST /auth/2fa/verify`, `ssoStartUrl` (hidden by flag) |
| Accept invite | `/invite` | `acceptInvitation` → `POST /auth/invitations/accept` |
| Sign up | `/login?mode=signup` | `signup` → `POST /auth/signup` |

### App (light, `AppShell`)
| Screen | Route | Session | API |
|---|---|---|---|
| Shell: sidebar, top bar, ⌘K, bell | all | 0 (shell), 6 (bell content) | `me`, `countUnreadAlerts`, `searchExceptions`, `listReports`, `listAlertsPage`, `acknowledgeAlert` |
| Home | `/overview` | 2 | `overview` → `GET /overview`, `workQueue` → `GET /work-queue`, `listObligations` → `GET /obligations`, `tenantAudit` → `GET /audit?limit=8`, `listReports` |
| Home empty state / onboarding | `/overview`, `/onboarding` | 2 | `uploadReport` with the bundled sample (`public/sample/Harbour_MGA_Claims_Aug_2026.xlsx`, from `demo/fixtures`) |
| Submissions | `/reports` | 2 | `listReports` → `GET /reports` (filters: see Gap G6) |
| New submission + processing | `/upload` | 2 | `uploadWithMeta`/`uploadWithProgress` → `POST /reports/upload`, `getReport`, `reportJobs` → `GET /reports/{id}/jobs`, `cancelReport`, `retryReport`, `counterparties` (sender select, Gap G9) |
| Mapping review | `/reports/[id]?view=mapping` (and from upload) | 3 | `listSheets`, `getSheetMappingFull` → `GET /reports/{id}/sheets/{sid}/mapping`, `confirmSheetMapping` (POST), `includeSheet`, `skipSheet`, `processReport` → `POST /reports/{id}/process`, `sheetGrid` (preview). Method chips add **Remembered** (`MAPPED_BY_MEMORY`, Phase 4). |
| Report header + VerdictStrip | `/reports/[id]` | 4 | `getReport`, `getReportSummary` → `GET /reports/{id}/summary`, `lib/verdict.ts` |
| Report · Review (root causes) | tab | 4 | `listIssues` → `GET /reports/{id}/issues` (`root_causes`, `by_status`, recurrence), `decideRootCause` → `POST /issues/bulk`, `getIssue` (lineage, corrections) |
| Report · Findings | tab | 4 | `listIssues` (flat), `listChecks`/`listModuleFindings` (binder, payments), `runCheck` |
| Finding drawer | overlay | 4 | `getIssue`, `POST /issues/{iid}/status`, `proposeCorrection`, `decideCorrection`, `disposeFinding` (module findings), `reviewException` (assign owner) |
| Report · Workbook | tab | 5 | `sheetGrid`, `gridTile`, `gridSearch`, `gridIssues`, `proposeCorrection`, `decideCorrection`, connectors: `listConnectors`, `connectorLinks`, `openInProvider`, `pullConnector`, `pushConnector` |
| Report · Claims | tab | 4 | `listClaimsByRef` → `GET /reports/{id}/claims` |
| Report · Mapping (read-only) | tab | 4 | `listSheets`, `getSheetMapping`; confirmer/time from `getAuditLog` |
| Report · Reconciliation | tab | 4 | `getReportSummary` (row counts), `listExcludedRows` → `GET /excluded-rows`, reconcile findings (`totals_mismatch`, `cross_sheet_conflict`, `paid_decreased`, `rollforward_break`) from `listIssues?rule=`, month-on-month `GET /reports/{id}/compare` |
| Report · Evidence | tab | 4 | `getAuditLog` → `GET /reports/{id}/audit`, `verifyAudit`, `auditPackUrl`, trail `GET /reports/{id}/trail`, versions `GET/POST /versions`, `/versions/{v}/approve`, `/versions/{v}/download`, corrections `GET /corrections`, `corrections/auto`, exports `exportClaimsUrl`, `exportExceptionsUrl`, `annotatedWorkbookUrl`, `correctedWorkbookUrl`, sender requests `GET /reports/{id}/requests`, `queryLetter`, deliveries `listDeliveries`, `sendDelivery` |
| Processing / failed report | `/reports/[id]` | 4 | same header, `reportJobs`, `retryReport` |
| Sample report (real screen) | `/sample-report` | 4 | static fixture through the same components |
| Findings queue | `/exceptions` | 6 | `searchExceptions`/`listExceptionsPage`, `exceptionGroups`, `reviewException`, issue status per report (Gap G3) |
| Duplicates (tab) | `/exceptions?tab=duplicates` | 6 | `listDuplicates` → `GET /reports/{id}/duplicates`, `reviewDuplicate` (`not_duplicate` / `flagged_for_sender` / `confirmed_duplicate`) |
| Sender queries (tab) | `/exceptions?tab=queries` | 6 | `GET /reports/{id}/requests` per report (Gap G4), `queryLetter`, CSV built client-side |
| Notifications popover | top bar | 6 | `listAlertsPage`, `acknowledgeAlert`, grouped client-side by `report_id` |
| Senders list | `/senders` | 7 | `GET /counterparties` |
| Sender profile | `/senders/[sender]` | 7 | `GET /counterparties/profile?sender=`, `GET /memory/rule-suggestions`, `POST /memory/rules` (approve reusable rule), `listReports` filtered client-side (G6) |
| Evidence · Audit trail | `/audit` (Evidence tab) | 7 | `tenantAudit` → `GET /audit` (50/page), `verifyAudit` → `GET /audit/verify` |
| Evidence · Exports & packs | `/exports` | 7 | `listDeliveries` → `GET /deliveries` (Gap G5) |
| Settings · Organisation | `/settings` | 7 | `getOrg`, `updateOrg` |
| Settings · Members | `?tab=members` | 7 | `listMembers`, `changeRole`, `removeMember`, `listInvitations`, `invite`, `revokeInvitation` |
| Settings · Security | `?tab=security` | 7 | `mfaStatus`, `mfaSetup`, `mfaEnable`, `mfaDisable`, org MFA flag via `updateOrg` |
| Settings · Channels | `?tab=channels` | 7 | `channels` → `GET /channels`, `getInbound`, `rotateInbound`, `getSftp`/`saveSftp`/`testSftp`/`removeSftp`, webhooks (if configured), `listConnectors` (Microsoft 365 / Google: "Connected" or "Available, needs setup") |
| Settings · Binders (Beta) | `?tab=binders` | 7 | `listBinders`, `createBinder`, `deleteBinder`, `assignBinder` → `PUT /reports/{id}/binder` |
| Settings · Templates | `?tab=templates` | 7 | `listTemplates`, `POST /templates` (kept; small) |
| System pages | 404, 403, 500, "Not available yet", maintenance | 8 | `systemStatus` → `GET /system/status` for maintenance |
| Sender portal | `/sender` | 8 | `senderPreflight`, `senderSubmit`, `senderSubmissions` |
| Hidden by flag | `/inbox`, `/todo`, `/duplicates`, `/alerts`, `/scorecard`, `/automations`, billing, SSO, sanctions | 0 (flags), 6/8 (pages) | Routes kept; nav removed; direct visit shows "Not available yet". |

---

## 3. Sessions

Status: Session 0 done (branch `frontend-redesign`). Top model for 0, 1, 4, 5. Each session ends with lint, typecheck, unit, build, its visual spec
(`tests/visual/<session>.spec.ts`, 1440 + 390, `scrollWidth <= 390`), screenshots in `docs/design/review/<session>/`, one commit.

| # | Builds | Read only |
|---|---|---|
| 0 | `styles/tokens.css`, `app/fonts.ts` (Inter, JetBrains Mono), `components/ds/*`, `MarketingShell`, `AppShell` (sidebar, top bar, ⌘K, bell shell), `lib/flags.ts`, `/design-system`, `colorContrast` pairs | spec §1–4, §6, §8, §10–11; `styles/*`, `app/layout.tsx`, both group layouts, `components/nocturne/{shell,ui,status}.tsx`, `components/layout/*`, `lib/colorContrast.ts` |
| 1 | Landing, `/health-check`, `/sample-report` (interim), `/security`, `/privacy`, `/crs` | spec §1–3, §5; `components/site/*`, `app/(marketing)/*`, `components/ds/index.ts` |
| 2 | `lib/verdict.ts`, `lib/findings.ts` adapters; Sign in/invite/MFA, Home (+ empty state, onboarding), Submissions, Upload + processing | spec §6–7.4, §9; `app/login`, `app/invite`, `app/onboarding`, `overview`, `reports/page.tsx`, `upload`, `components/nocturne/{intake,report-list,ops}.tsx`, `lib/api.ts` signatures, `lib/types.ts` |
| 3 | Mapping review | spec §7.5; mapping parts of `components/nocturne/intake.tsx`, `workbook-preview.tsx`, mapping types |
| 4 | Report header, VerdictStrip, Review/Findings/Claims/Mapping/Reconciliation/Evidence tabs, finding drawer, `/sample-report` on the real screen, verdict fixtures | spec §7.6–7.7, §9; `reports/[reportId]/page.tsx`, `components/nocturne/{review-queue,checks}.tsx`, report/issue types |
| 5 | Workbook tab: grid restyle, inspector, corrections inline, connectors (open in Excel/Sheets, pull, push) | `components/nocturne/workbook-grid.tsx`, grid/connector types |
| 6 | Findings queue, Duplicates comparison, Sender queries, notifications popover, hide `/duplicates` `/alerts`, `formatMoney` only | spec §6 (bell), §7.8; `exceptions`, `duplicates`, `alerts` pages, `lib/formatters.ts` |
| 7 | Senders + profile, Evidence (audit, exports), Settings (all tabs), Binders Beta | spec §7.9–7.11; `audit`, `exports`, `settings` pages, `components/nocturne/settings.tsx` |
| 8 | System pages, sender portal restyle, a11y + 390px pass across the app, product screenshots into `public/product/`, delete old UI (`components/nocturne`, `components/site`, Tailwind, Phosphor), final screenshots | spec §7.12, §10–11 |

---

## 4. Backend gaps (front end works around them; none are changed here)

| ID | Gap | Front-end handling |
|---|---|---|
| G1 / D1 | No `GET /reports/{id}/verdict`. `health_view` returns only "fix"/"ready". | `lib/verdict.ts` derives the verdict from summary + issues + module findings (`// TEMPORARY`). `claims` flag line stays off. |
| G2 / D10 | Engine issues (`/issues`) and module findings (`/checks/findings`) are separate lists. | `lib/findings.ts` unions them (`// TEMPORARY`). |
| G3 | No cross-report issues endpoint with the Phase 1 lifecycle; `GET /exceptions` search returns the older `review_status` model. | Findings queue shows `review_status` mapped to lifecycle words; decisions open the report's drawer. |
| G4 | Sender requests (`[TB-n]`) are per report only; no tenant-wide list. | Queries tab fans out over recent reports (max 25) and says so. |
| G5 | No list of generated exports/audit packs (downloads are streamed, not recorded as files). | Exports tab lists deliveries plus audit entries of export actions; no file sizes. |
| G6 | `GET /reports` filtering by sender/status/verdict/date is limited; no owner field on reports. | Filters applied client-side to the loaded page; owner column omitted. |
| G7 | No comments on findings. | Drawer shows status history and notes; no comment box. |
| G8 / D7 | Mapping confirm takes no "process anyway, grade withheld" acknowledgement. | Normal confirm after the modal, `// TODO backend D7`. |
| G9 | No programmes list endpoint. | Free-text programme with recent values from `listReports`; sender select from `GET /counterparties`. |
| G10 / D2 | "Every source row accounted for" needs subtotal-row accounting. `excluded-rows` exists. | Session 4 checks whether excluded rows + claims = source rows on the A1 sample; flag stays off until proven. |
| G11 | Hosting claims ("EU-hosted", "encrypted at rest", "daily backups"). Render Frankfurt is EU, but backups/encryption aren't documented as live. | Behind `claims` flag. |
| G12 | Notifications have no read state per user; `acknowledge` is per alert. | "Mark all read" acknowledges each alert in the open group. |
| G13 | Migrations 0022–0024 aren't on production. | Phase 3–5 screens (corrections policy, memory, connectors) work only against a `rebuild` backend. |
