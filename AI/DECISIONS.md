# Decisions log

Append-only. Each entry: what was decided, why, and what the alternative
was. Don't delete old entries even if later superseded — add a new entry
that says so.

---

## 2026-09-17 — Fixed `.xls` support with `xlrd`, rather than dropping `.xls` from the supported-formats list

**Decision:** Add `xlrd>=2.0` as a real dependency and give
`bordereaux/src/bordereaux/ingest.py` a genuine legacy-binary-format
reader, rather than just removing `.xls` from `ALLOWED_SUFFIXES` (which
would have "fixed" the error by no longer promising something that didn't
work).

**Why:** The task brief explicitly required `.xls` support, and legacy
binary Excel is common for older-generation claims/bordereaux systems —
exactly this product's target data source. Silently dropping support
would have been the "fake frontend-only workaround" the brief explicitly
warned against; it would move the failure from "confusing error after
drop" to "file picker silently rejects it," which is not actually fixing
anything for a user whose only file is a real `.xls`.

**Alternative considered:** Ask the user to always re-save as `.xlsx`
before uploading. Rejected — that's a support burden on every affected
user for a problem that has a small, well-scoped code fix.

---

## 2026-09-17 — Added `.xlsm` to the supported-format list in the same pass

**Decision:** `.xlsm` (macro-enabled workbook) was not in the original
`ALLOWED_SUFFIXES`/`accept` list at all, despite `openpyxl` already
reading it correctly (it's the same zip/XML container as `.xlsx` with an
extra macro part) — so this was a zero-risk, one-line extension of the
exact same "extension gate doesn't match parser capability" bug class
already being fixed.

**Why folded into this pass rather than deferred:** The brief's own
framing ("the upload system needs to support X, Y, Z" + "fix the
underlying upload problem" comprehensively) plus the fact that `.xlsm` is
a very ordinary real-world bordereau extension (any workbook with even one
macro, however unrelated to the data, saves as `.xlsm` by default) made
this a same-root-cause fix, not scope creep into a new feature. If a
future reviewer disagrees, reverting is a two-line change (remove
`.xlsm` from `ALLOWED_SUFFIXES` and the frontend `accept` string) — no
data model or pipeline change depends on it.

---

## 2026-09-17 — Did not pin `pandas` to a pre-3.0 version

**Decision:** Left `pandas>=2.2` unpinned in `bordereaux/pyproject.toml`
despite a fresh install resolving to `pandas==3.0.5` and pandas 3.0 being
a major version with documented breaking changes upstream.

**Why:** Every existing test (`bordereaux`'s phase tests, boundary
fixture, and `truebind-web`'s pytest suite) passed against 3.0.5 with no
code changes needed. Pinning defensively against a version that
demonstrably works, without a specific failure to point to, would be
adding a constraint on guesswork rather than evidence — the opposite of
this session's "fix what's actually broken, verify what you claim" brief.

**What a future session should do instead of re-litigating this:** If a
pandas-version-shaped bug shows up, check whether it's specific to 3.x
behavior (e.g., copy-on-write semantics, `errors="ignore"` removal, string
dtype defaults) before assuming it's unrelated. This is flagged in
`TODO.md` as a watch item, not left silent.

---

## 2026-09-17 — Visual redesign: serif system-font stack, not a webfont

**Decision:** `--font-display` (used for `h1`/`h2`/eyebrow labels) is a
portable serif stack — `Iowan Old Style, "Source Serif Pro", Georgia,
Cambria, "Times New Roman", serif` — not a `next/font/google` load.

**Why:** The brief called for "typography-led" hierarchy and explicitly
rejected "generic Inter/Arial-style visual treatment" — a serif face for
headings against a sans body is a deliberate, legible way to get that
without inventing a new UI-component vocabulary. A real webfont would
look more considered on a machine that already has it, but:
1. `next/font/google` needs network access at build time to fetch and
   self-host the font; this repo's CI/dev-environment network posture
   wasn't something this session could verify holds everywhere the app
   gets built, and a build-time network dependency for pure decoration is
   a real fragility to introduce for a cosmetic upgrade.
2. The fallback chain (Georgia/Cambria are near-universal on
   macOS/Windows/Linux with fontconfig) already reads as a deliberate
   editorial serif, not a "default browser serif" look, in every
   environment this was tested in.

**What a future session should do if this matters:** If self-hosting a
real serif (e.g., Source Serif 4 or Newsreader via `next/font/google`) is
wanted, confirm the target deploy environment allows the build-time fetch
first, then swap only the `--font-display` value and font-loading
mechanism — no other file depends on this being a system stack
specifically.

---

## 2026-09-17 — Kept the existing color token *values*; changed only how badges/cards apply them

**Decision:** Did not touch any hex value in `styles/variables.css` or
`lib/colorContrast.ts`. Changed `Badge`/`MetricCard` from filled
backgrounds to hairline-bordered/hollow treatments using the same tokens.

**Why:** The existing palette was already WCAG-AA validated at build time
(`lib/colorContrast.ts`, enforced via a throw in `app/layout.tsx` at
module-eval time) and already kept four status-color families
deliberately distinct (mapping tri-state / arithmetic outcome / leakage
confidence / sanctions — see the comment at the top of `variables.css`).
Changing hex values would have required re-deriving and re-verifying every
contrast pair; changing *usage* achieved the brief's "avoid excessive
pill-shaped UI, avoid a state looking like a clean pass" goals without
touching a system that was already correct. This is the same
"preserve working logic unless it genuinely needs to change" instruction
applied to CSS, not just Python.

---

## 2026-09-17 — Did not create a new component abstraction for "stat block" or "step list"

**Decision:** The typographic stat treatment (used for Reports' four
top-line metrics) stayed inside the existing `MetricCard` component
(`components/ui/Card.tsx`) with restyled CSS, rather than becoming a new
`Stat` component. The upload page's numbered 01/02/03 explainer became a
plain `.stepList`/`.stepNumber` utility class pair in `globals.css`
(used once, in `upload/page.tsx`), not a new `<StepList>` component.

**Why:** Per the task's own engineering guidance — no premature
abstraction for a pattern used in one or two places. If a third screen
needs the same numbered-steps treatment, that's the point to extract a
component; inventing one now for a single call site would be exactly the
unnecessary abstraction the brief warns against.
