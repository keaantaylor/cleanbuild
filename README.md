# Handoff: LaunchPoint Marketing Website

## Overview
LaunchPoint is a Dublin-based web design and digital support company selling affordable, subscription-managed websites to Irish small businesses (salons, plumbers, accountants, cafés, etc.). This design is their own marketing website. Primary conversion goal: **get visitors to book a free discovery call** — every page ends in a "Book a free call" CTA.

## About the Design Files
The files in this bundle are **design references created in HTML** — prototypes showing intended look and behavior, not production code to copy directly. Your task is to **recreate these designs in the target codebase's existing environment** (React, Next.js, Astro, plain HTML/CSS — whatever the project uses) with its established patterns. If no codebase exists yet, choose an appropriate stack for a small marketing site (a static or SSR framework like Astro or Next.js is a good fit) and implement the designs there.

`LaunchPoint Site.dc.html` contains **two things**:
1. **Turn 2 (`id="2a"`) — the authoritative build-out.** A full multi-page site (Home, Services, How it works, Pricing, FAQ, Book a call) with working header/footer navigation. **This is what should be implemented.**
2. Turn 1 (`id="1a"`, `1b`, `1c`) — three earlier single-page style explorations. `1a` ("Boardroom clean") is the chosen direction and is what 2a is built from. `1b`/`1c` are for reference only; do not implement.

All styling is inline on each element, so exact values can be read directly from the markup. The 2a markup starts at the `<section class="dv-turn" id="t2">` block near the top of the file; page templates are the `<sc-if>` blocks (Home, Services, How it works, Pricing, FAQ, Book a call), and the navigation/state logic is the `class Component extends DCLogic` script at the bottom.

## Fidelity
**High-fidelity.** Colors, typography, spacing, copy and layout are final. Recreate faithfully at desktop width (1240px content canvas). Responsive/mobile behavior was NOT designed — implement sensible stacking (grids collapse to 1 column, header nav collapses to a menu) using the codebase's conventions.

## Design Tokens

### Colors
| Token | Value | Use |
|---|---|---|
| Navy (ink) | `#0f1f3d` | Headings, dark bands, form card, footer wordmark |
| Primary blue | `#1f66d6` | CTAs, links, accents, active nav, featured tier |
| Blue hover | `#1a56b5` | Primary button hover |
| Blue tint | `#e6effc` | Icon/number badges, "in every plan" pill |
| Body text | `#4a5670` | Paragraphs |
| Secondary text | `#3c4a63` | Nav links, checklist items, quotes |
| Muted | `#7a8499` | Captions, footnotes, footer |
| Muted on navy | `#aab6cc` | Subheads on `#0f1f3d` bands |
| Surface | `#f4f6f9` | Alternating section backgrounds |
| Border | `rgba(15,31,61,0.08)`–`0.12` | Card borders, dividers |

### Typography
- Font: **Manrope** (Google Fonts), weights 400–800; system-ui fallback.
- H1 (page hero): 46–58px / 800 / line-height 1.08–1.1 / `#0f1f3d`, `text-wrap: balance`.
- Section heading: 36px / 800. Card title: 19–23px / 800.
- Eyebrow: 13.5–14px / 700 / uppercase / letter-spacing 0.12em / `#1f66d6`.
- Body: 15.5–18px / line-height 1.6–1.7 / `#4a5670`.
- Buttons: 15–17px / 700.

### Shape & spacing
- Cards radius 12–14px; CTA cards 16px; buttons 8–9px; pills/badges 99px.
- Section padding: 88px vertical / 64px horizontal (heroes 160px, narrow text pages 200px horizontal).
- Grid gaps 20–24px; featured-tier shadow `0 12px 32px rgba(31,102,214,0.14)`; primary button shadow `0 4px 14px rgba(31,102,214,0.28)`.

## Site Structure & Routing
Six routes sharing one header and footer:

- `/` Home
- `/services` Services
- `/how-it-works` How it works
- `/pricing` Pricing
- `/faq` FAQ
- `/book-a-call` Book a call

In the prototype, navigation is client-side state (`page`). In production, use real routes. Active header link: `#1f66d6`; inactive: `#3c4a63`; hover: `#1f66d6`.

## Shared Chrome

### Header (all pages)
- White bar, `padding: 20px 64px`, bottom border `1px solid rgba(15,31,61,0.08)`.
- Left: logo image (`assets/launchpoint-logo.png`), height 42px, links to `/`.
- Right: flex row, gap 36px, links (15px/600): Services, How it works, Pricing, FAQ, then primary button **"Book a free call"** — `background:#1f66d6; color:#fff; padding:12px 24px; border-radius:8px; font-weight:700`, hover `#1a56b5`.

### Footer (all pages)
- `padding: 28px 64px`, top border, 14px `#7a8499`, space-between.
- Left: wordmark "Launch**Point**" (800, `#0f1f3d`, "Point" in `#1f66d6`).
- Center: nav links (all 5 pages), gap 28px, 600 weight, hover blue.
- Right: "Dublin, Ireland · hello@launchpoint.ie · © 2026".

## Screens

### 1. Home (`/`)
1. **Hero** — centered, `padding:104px 160px 88px`. Eyebrow "Web design & management · Dublin, Ireland". H1 58px, max-width 820px: "Affordable websites. Ongoing support. Zero hassle." Subhead 20px, max-width 640px. Buttons: primary "Book a free call" (padding 17px 34px, radius 9px, shadow) → `/book-a-call`; secondary outline "See pricing" → `/pricing`. Trust row 14.5px/600 `#7a8499`: "✓ From €349 · ✓ Live within days · ✓ Updates included".
2. **Problem** — `#f4f6f9` band. Heading "No website is costing you customers — every single week." 3 white cards: "They're Googling you" / "A Facebook page isn't enough" / "Out-of-date is worse than nothing".
3. **Services teaser** — white. Eyebrow "What we do", heading "Everything your business needs online". 2×2 bordered cards with numbered badges (44×44, radius 10, `#e6effc`/`#1f66d6`, "01"–"04"): Website design / Online booking / Website management / Digital growth. Centered link "See everything included →" → `/services`.
4. **How it works teaser** — `#f4f6f9`. 3 white cards with giant 44px number: Book a free call / Pick from three designs / Go live — we take it from there. Link "See the full process →" → `/how-it-works`.
5. **Pricing teaser** — white. 3 compact clickable cards (→ `/pricing`), middle featured (2px blue border + shadow). Link "Compare plans in detail →".
6. **Testimonials** — `#f4f6f9`. "Trusted by businesses like yours". 3 cards: blue ★★★★★, quote, name + business. **Placeholder content — swap for real testimonials.**
7. **CTA band** — `#0f1f3d`, centered: "Ready to get your business online?" + sub + primary button.

### 2. Services (`/services`)
1. Hero: eyebrow "Services", H1 "Everything your business needs online — handled for you".
2. 2×2 large cards (radius 14, padding 40): **Website design** (8-item ✓ checklist in 2 cols); **Online booking** ("Perfect for" pill row: Hair salons, Barbers, Therapists, Beauticians, Tutors, Consultants, Tradespeople); **Website management** + "IN EVERY PLAN" blue-tint pill + 8-item checklist; **Digital growth** + "ADD-ONS" gray pill + 7-item checklist.
3. **Industries we serve** — `#f4f6f9` band: ~22 white outline pills (Accountants … Consultants, "+ more"), then "Don't see your industry? **Ask us on a free call.**" → `/book-a-call`.
4. Navy CTA card (radius 16): "Not sure what your business needs? That's what the free call is for." + button.

### 3. How it works (`/how-it-works`)
1. Hero: H1 "From first call to launch — in days, not months".
2. **6-step vertical list** (narrow, 200px side padding). Each row: 48px circle number (steps 1–3 navy, 4–6 blue), title 21px/800, body, right timing pill: Free discovery call (Day 1 · 20 min) / Three homepage concepts (Days 2–3) / You choose your direction (5 minutes) / We build your website (Days 4–6) / Launch (Launch day) / Ongoing support, forever (Every month — blue pill). Divider rules between rows.
3. **"All we need from you"** — `#f4f6f9`, 2-col: checklist (20 minutes on the phone; logo + photos; a yes/no on the design) + white card "Ready to start the clock?" with primary button.

### 4. Pricing (`/pricing`)
1. Hero: H1 "Simple, transparent pricing", sub: month to month, cancel anytime, no hourly rates.
2. **3 tier cards** (radius 14, padding 36, 2px border):
   - **Launch Starter** — €349 setup + €39/mo. ✓ Up to 4 pages, Contact form, Mobile optimisation, Monthly edits, Hosting management.
   - **Launch Business** (featured default) — €699 setup + €79/mo. ✓ Up to 10 pages, Online booking integration, Basic SEO, Google Maps, Monthly updates, Priority support.
   - **Launch Growth** — €1,199 setup + €149/mo. ✓ Everything in Business, Google Ads setup, Social media advertising, Advanced SEO, Landing pages, Quarterly optimisation review.
   - Featured: blue border, shadow, floating "MOST POPULAR" pill on top edge, solid blue button. Others: light border, outline button. Prices 40px/800. Buttons "Start with a call" → `/book-a-call`.
3. **"Every plan includes"** — `#f4f6f9`, 2-col: 5-item checklist + 3 mini-FAQs (Switch plans later? / What does setup cover? / What if I cancel?).
4. Navy CTA card: "Not sure which plan fits? We'll tell you honestly on the call."

### 5. FAQ (`/faq`)
1. Hero: H1 "Questions we hear all the time".
2. **8 Q&A rows** (200px side padding, divider rules). Questions styled as quoted objections, 18px/800: "I don't have time for this." / "I don't know what I want it to look like." / "Isn't a website expensive?" / "What happens when my prices or hours change?" / "Am I locked into a contract?" / "Do I own my website and domain?" / "I already have an old website." / "Who writes the text on the site?" — exact answers are in the HTML.
3. Navy CTA band: "Still have a question?" + button.

### 6. Book a call (`/book-a-call`)
Two-column (gap 72px):
- **Left**: eyebrow "Book a call", H1 "Let's talk about your business", intro, then 3 numbered expectation rows (40px blue-tint circles): We call you back / A 20-minute chat / Three free concepts. Bottom: "Prefer email? **hello@launchpoint.ie**".
- **Right**: navy form card (`#0f1f3d`, radius 16, padding 44). "Request your free call". Fields (white, borderless, radius 9): Your name, Business name, Phone number, optional textarea. Full-width blue submit "Request my free call". Footnote: "We'll call you back within one working day. No spam, ever."
- **Form submission is not implemented** — wire to the project's form/email/CRM backend; validate name + phone as required; show a confirmation on success.

## Interactions & Behavior
- Every CTA ("Book a free call", "Start with a call", CTA cards) → `/book-a-call`.
- Header/footer links navigate; active header link blue.
- Hovers: primary buttons → `#1a56b5`; outline buttons gain blue border/text; text links underline; nav links blue. ~150ms ease color transition is appropriate (none specified).
- Home pricing teaser cards fully clickable; non-featured get blue border on hover.
- No other loading/error/empty states designed.

## Configurable Values (from the prototype's props)
The prototype exposes three knobs; treat them as site config, not per-user state:
- `ctaLabel` (default "Book a free call") — the label used on every primary CTA.
- `featuredTier` (default "business") — which pricing card gets the featured treatment (border, shadow, "Most popular" pill, solid button).
- `page` — prototype-only route switcher; replace with real routing.

## Assets
- `assets/launchpoint-logo.png` — full logo (rocket + wordmark), used in header at 42px height. On dark backgrounds the text wordmark ("LaunchPoint" typed in white/blue) is used instead of the image.
- No other imagery. Do not add stock photos without asking the client.

## Files in This Package
- `README.md` — this document
- `LaunchPoint Site.dc.html` — full design source (turn 2a = authoritative; turn 1 = explorations). Open in a browser to view it; click the header links to switch pages. All styles are inline in the markup.
- `assets/launchpoint-logo.png` — logo

## Suggested Claude Code prompt
> Implement the LaunchPoint marketing site described in `design_handoff_launchpoint_site/README.md`, using the design source in `LaunchPoint Site.dc.html` (section `id="2a"` only) as the visual reference. Match colors, spacing and copy exactly at desktop width; add sensible responsive stacking. Use [your framework] with real routes for the six pages and wire the booking form to [your backend].
