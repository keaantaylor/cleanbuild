import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";

/* TrueBind product demo: the real application, a synthetic bordereau, one take.
 *
 * Journey: login -> overview -> intake (upload + mapping) -> processing ->
 * workbook (issue cells, expected vs actual) -> review (root cause) ->
 * health check -> mapping -> lineage -> audit trail.
 *
 * Output (demo/output/): shots/NN-name.png, frames/ (screencast), and
 * truebind-demo.mp4 (H.264, 1920x1080, 30 fps) when FFMPEG is set; the
 * Playwright WebM is kept as a fallback. Pauses are generous on purpose: the
 * edit cuts the take down to about 60 seconds.
 */

const OUT = path.resolve(__dirname, "output");
const WORKBOOK = path.resolve(__dirname, "workbooks/Coastline_MGA_Claims_Bordereau_Sep_2026.xlsx");
const PRIOR = path.resolve(__dirname, "workbooks/Harbour_MGA_Claims_Bordereau_Aug_2026.xlsx");
// A throwaway account in a throwaway local database. Not a real person or customer.
const DEMO = { email: "analyst@demo.truebind.example", password: "Demo-only passphrase 2026", name: "Demo Analyst", org: "Demo Syndicate" };

const PACE = Number(process.env.DEMO_PACE ?? 1); // 0.5 for a quick rehearsal

const hold = (page: Page, ms: number) => page.waitForTimeout(ms * PACE);

/** A visible pointer: headless Chromium draws none, and clicks without one look like jump cuts. */
async function installCursor(page: Page) {
  await page.addInitScript(() => {
    const draw = () => {
      if (document.getElementById("__demo_cursor")) return;
      const c = document.createElement("div");
      c.id = "__demo_cursor";
      c.setAttribute("aria-hidden", "true");
      Object.assign(c.style, {
        position: "fixed", left: "0px", top: "0px", width: "18px", height: "18px", borderRadius: "50%", zIndex: "2147483647",
        background: "rgba(17,24,39,0.18)", border: "2px solid rgba(17,24,39,0.75)", pointerEvents: "none",
        transform: "translate(-9px,-9px)", transition: "transform 80ms ease-out, background 80ms",
      });
      document.body.appendChild(c);
      window.addEventListener("mousemove", (e) => { c.style.left = `${e.clientX}px`; c.style.top = `${e.clientY}px`; }, true);
      window.addEventListener("mousedown", () => { c.style.background = "rgba(31,79,209,0.35)"; c.style.transform = "translate(-9px,-9px) scale(0.85)"; }, true);
      window.addEventListener("mouseup", () => { c.style.background = "rgba(17,24,39,0.18)"; c.style.transform = "translate(-9px,-9px)"; }, true);
    };
    if (document.body) draw();
    else document.addEventListener("DOMContentLoaded", draw);
  });
}

async function moveTo(page: Page, target: Locator) {
  await target.scrollIntoViewIfNeeded();
  const box = await target.boundingBox();
  if (!box) throw new Error("target has no box");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 22 });
  await hold(page, 180);
}

async function click(page: Page, target: Locator) {
  await moveTo(page, target);
  await target.click();
}

async function typeInto(page: Page, target: Locator, text: string) {
  await click(page, target);
  await target.pressSequentially(text, { delay: 38 });
}

/** Smooth scroll of the page (or a scroller) by dy pixels. */
async function glide(page: Page, dy: number, steps = 30) {
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, dy / steps);
    await page.waitForTimeout(16);
  }
}

/** Scroll instantly so the target sits `offset` px below the top bar (no scrolling past content on camera). */
async function toTop(page: Page, target: Locator, offset: number) {
  await target.evaluate((el, off) => window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - off }), offset);
  await page.waitForTimeout(250);
}

async function shot(page: Page, name: string) {
  await page.screenshot({ path: path.join(OUT, "shots", `${name}.png`) });
}

/** Off camera: the demo account and one earlier bordereau from another sender, so the overview has history. */
async function seed(request: APIRequestContext) {
  const r = await request.post("/api/v1/auth/signup", { data: { email: DEMO.email, password: DEMO.password, display_name: DEMO.name, organisation: DEMO.org } });
  expect(r.status(), await r.text()).toBe(201);
  const csrf = { "X-CSRF-Token": (await r.json()).csrf_token as string };
  const up = await request.post("/api/v1/reports/upload", {
    headers: csrf,
    multipart: { file: { name: path.basename(PRIOR), mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: (await import("node:fs")).readFileSync(PRIOR) }, sender: "Harbour MGA" },
  });
  expect(up.status(), await up.text()).toBe(202);
  const rid = (await up.json()).id as string;
  const status = async () => (await (await request.get(`/api/v1/reports/${rid}`)).json()).status as string;
  await expect.poll(status, { timeout: 120_000 }).toBe("WAITING_FOR_REVIEW");
  for (const s of await (await request.get(`/api/v1/reports/${rid}/sheets`)).json()) {
    if (s.status === "SKIPPED") continue;
    const m = await (await request.get(`/api/v1/reports/${rid}/sheets/${s.id}/mapping`)).json();
    const choices = Object.fromEntries(m.fields.map((f: { field_code: string; source_column: string | null }) => [f.field_code, f.source_column]));
    expect((await request.post(`/api/v1/reports/${rid}/sheets/${s.id}/mapping`, { headers: csrf, data: { mappings: choices } })).ok()).toBeTruthy();
  }
  expect((await request.post(`/api/v1/reports/${rid}/process`, { headers: csrf })).status()).toBe(202);
  await expect.poll(status, { timeout: 180_000 }).toBe("COMPLETE");
  await request.post("/api/v1/auth/logout", { headers: csrf });
}

test("TrueBind product demo", async ({ page, request }) => {
  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(path.join(OUT, "shots"), { recursive: true });
  mkdirSync(path.join(OUT, "frames"), { recursive: true });
  await seed(request);
  await installCursor(page);

  // Screencast: every painted frame as a high-quality JPEG with its timestamp.
  const cdp = await page.context().newCDPSession(page);
  const frames: { file: string; t: number }[] = [];
  cdp.on("Page.screencastFrame", async (f) => {
    const file = path.join(OUT, "frames", `${String(frames.length).padStart(6, "0")}.jpg`);
    writeFileSync(file, Buffer.from(f.data, "base64"));
    frames.push({ file, t: f.metadata.timestamp ?? Date.now() / 1000 });
    await cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => undefined);
  });
  const marks: { at: number; label: string }[] = [];
  const t0 = Date.now();
  const mark = (label: string) => marks.push({ at: (Date.now() - t0) / 1000, label });

  // 1. Login ---------------------------------------------------------------
  await page.goto("/login");
  await page.mouse.move(960, 700);
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });
  mark("01 login");
  await hold(page, 900);
  await typeInto(page, page.getByLabel("Work email"), DEMO.email);
  await typeInto(page, page.getByLabel("Password"), DEMO.password);
  await shot(page, "01-login");
  await click(page, page.getByRole("button", { name: "Sign in", exact: true }));

  // 2. Overview --------------------------------------------------------------
  await expect(page).toHaveURL(/\/overview/);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.waitForLoadState("networkidle");
  mark("02 overview");
  await hold(page, 2200);
  await shot(page, "02-overview");

  // 3. Intake: a messy coverholder file, read and mapped -----------------------
  await click(page, page.getByRole("link", { name: "Intake" }).first());
  await expect(page).toHaveURL(/\/upload/);
  mark("03 intake");
  await hold(page, 700);
  await typeInto(page, page.getByLabel("Sender (optional)"), "Coastline MGA");
  await typeInto(page, page.getByLabel("Programme / account (optional)"), "Property binder 2026");
  await moveTo(page, page.locator("input[type=file]").locator(".."));
  await page.setInputFiles("input[type=file]", WORKBOOK);
  const confirmAll = page.getByRole("button", { name: /Confirm all as proposed/ });
  await expect(confirmAll).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText(/columns mapped automatically/)).toBeVisible();
  mark("04 mapping");
  await hold(page, 2600);
  await shot(page, "03-mapping");
  await click(page, confirmAll);
  const produce = page.getByRole("button", { name: "Produce health report" });
  await expect(produce).toBeVisible({ timeout: 60_000 });
  await hold(page, 500);
  await click(page, produce);

  // 4. Processing: the job's real stages, as the engine reports them ------------
  await expect(page.getByText("Validating every row")).toBeVisible({ timeout: 60_000 });
  mark("05 processing");
  await page.mouse.move(1500, 700, { steps: 12 });
  // Shoot once the engine is past reading the file, so the list shows real progress.
  const stage = page.getByText(/^Engine stage [4-8] of 9$/);
  if (await stage.waitFor({ timeout: 60_000 }).then(() => true, () => false)) await shot(page, "04-processing");
  await expect(page).toHaveURL(/\/reports\/[^/]+$/, { timeout: 180_000 });

  // 5. Workbook: the spreadsheet itself, every flagged cell named ---------------
  const grid = page.getByRole("grid");
  await expect(grid).toBeVisible({ timeout: 180_000 });
  await expect(page.getByText(/[\d,]+ rows · \d+ columns/)).not.toHaveText(/^0 rows/, { timeout: 60_000 });
  await expect(grid.getByRole("gridcell").filter({ hasText: /CLM-/ }).first()).toBeVisible();
  await page.waitForLoadState("networkidle");
  mark("06 workbook");
  await hold(page, 1800);
  const next = page.getByRole("button", { name: "Next issue" });
  await click(page, next);
  await hold(page, 1600);
  await click(page, next);
  await expect(page.getByLabel("Cell inspector")).toContainText(/Requires reconciliation|Undetermined/);
  await hold(page, 2400);
  await shot(page, "05-workbook-issue-cell");
  // Only the rows with a flagged cell: 5,000 rows narrowed to the ones that need attention.
  await click(page, page.getByLabel("Rows with issues only"));
  await expect(grid.getByRole("gridcell").filter({ hasText: /CLM-/ }).first()).toBeVisible();
  await hold(page, 600);
  await click(page, next);
  await hold(page, 2400);
  await shot(page, "05b-workbook-issues-only");

  // 6. Review: one decision per root cause --------------------------------------
  await click(page, page.getByRole("tab", { name: "Review issues" }));
  await expect(page.getByText(/^Issue 1 of \d+/)).toBeVisible();
  mark("07 review");
  await hold(page, 2600);
  await click(page, page.getByRole("button", { name: /affected cells/ }));
  await hold(page, 1800);
  await shot(page, "06-review-root-cause");

  // 7. Health check -----------------------------------------------------------
  await page.mouse.move(960, 300, { steps: 15 });
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await hold(page, 500);
  await click(page, page.getByRole("tab", { name: "Full report" }));
  await expect(page.getByRole("region", { name: "Verdict" })).toBeVisible();
  mark("08 health check");
  await hold(page, 2400);
  await shot(page, "07-health-check");
  await page.mouse.move(960, 600, { steps: 10 });
  await glide(page, 420);
  await hold(page, 2200);

  // 8. Mapping and lineage: where every number came from -------------------------
  const tabs = page.getByRole("tablist", { name: "Report sections" });
  await toTop(page, tabs, 90);
  await click(page, page.getByRole("tab", { name: "Mapping" }));
  await hold(page, 600);
  await toTop(page, tabs, 90);
  mark("09 mapping completeness");
  await hold(page, 2400);
  await shot(page, "08-mapping-completeness");
  await click(page, page.getByRole("tab", { name: "Other checks & evidence" }));
  // The checks above load after the tab opens and push the lineage section down: settle, then scroll.
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1200);
  const lineageHeading = page.getByRole("heading", { name: "Where every number came from" });
  await toTop(page, lineageHeading, 120);
  await page.waitForLoadState("networkidle");
  await toTop(page, lineageHeading, 120);
  await page.mouse.move(960, 500, { steps: 10 });
  mark("10 lineage");
  await hold(page, 2800);
  await shot(page, "09-lineage");

  // 9. Audit trail -----------------------------------------------------------
  await click(page, page.getByRole("link", { name: "Audit trail" }).first());
  await expect(page).toHaveURL(/\/audit/);
  await page.waitForLoadState("networkidle");
  mark("11 audit trail");
  await hold(page, 3000);
  await shot(page, "10-audit-trail");
  await cdp.send("Page.stopScreencast");

  writeFileSync(path.join(OUT, "timeline.json"), JSON.stringify({ marks, frames: frames.length }, null, 2));
  encode(frames);
});

/** Frames -> constant 30 fps H.264, each frame held until the next one was painted. */
function encode(frames: { file: string; t: number }[]) {
  const ffmpeg = process.env.FFMPEG;
  if (!ffmpeg || frames.length < 2) return;
  const lines = ["ffconcat version 1.0"];
  frames.forEach((f, i) => {
    const dur = i + 1 < frames.length ? Math.max(0.001, frames[i + 1].t - f.t) : 1.5;
    lines.push(`file '${path.basename(f.file)}'`, `duration ${dur.toFixed(4)}`);
  });
  lines.push(`file '${path.basename(frames[frames.length - 1].file)}'`);
  const list = path.join(OUT, "frames", "list.ffconcat");
  writeFileSync(list, lines.join("\n"));
  execFileSync(ffmpeg, ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list, "-vf", "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p",
    "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-movflags", "+faststart", path.join(OUT, "truebind-demo.mp4")], { stdio: "inherit" });
}
