import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { reviewDir, signUp, VIEWPORTS } from "./helpers";

// Unify review: landing (local and live), upload, mapping, report and workbook at 1440,
// plus end-to-end processing times for the stress workbooks.
//   VISUAL_BASE_URL=http://localhost:3001 VISUAL_API_URL=http://localhost:3001/api/v1 \
//   npx playwright test -c playwright.visual.config.ts tests/visual/unify.spec.ts
const S = "unify";
const API = process.env.VISUAL_API_URL ?? "http://localhost:8000/api/v1";
const DOWNLOADS = process.env.STRESS_DIR ?? "C:/Users/keala/Downloads";
const shot = (page: Page, name: string) => page.screenshot({ path: path.join(reviewDir(S), `${name}.png`), fullPage: true });

async function csrf(req: APIRequestContext): Promise<string> {
  return (await (await req.get(`${API}/auth/me`)).json()).csrf_token;
}

async function waitFor(req: APIRequestContext, id: string, done: (s: string) => boolean, timeoutS: number): Promise<string> {
  for (let i = 0; i < timeoutS * 2; i++) {
    const r = await (await req.get(`${API}/reports/${id}`)).json();
    if (done(r.status)) return r.status;
    await new Promise((res) => setTimeout(res, 500));
  }
  throw new Error(`report ${id} did not finish in ${timeoutS}s`);
}

/** Upload → mapping proposed → every pending sheet confirmed as proposed → processed. Returns seconds per phase. */
async function processFile(req: APIRequestContext, file: string) {
  const token = await csrf(req);
  const t0 = Date.now();
  const up = await req.post(`${API}/reports/upload`, {
    headers: { "X-CSRF-Token": token },
    multipart: { sender: "Stress Test MGA", file: { name: path.basename(file), mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: fs.readFileSync(file) } },
  });
  expect(up.status(), await up.text()).toBe(202);
  const id = (await up.json()).id as string;
  const afterIngest = await waitFor(req, id, (s) => !["UPLOADED", "QUEUED", "INGESTING", "RETRYING"].includes(s), 900);
  const t1 = Date.now();
  expect(afterIngest).toBe("WAITING_FOR_REVIEW");
  const sheets = await (await req.get(`${API}/reports/${id}/sheets`)).json();
  for (const s of sheets.filter((x: { status: string }) => x.status === "PENDING_CONFIRMATION")) {
    const m = await (await req.get(`${API}/reports/${id}/sheets/${s.id}/mapping`)).json();
    const mappings = Object.fromEntries(m.fields.map((f: { field_code: string; source_column: string | null }) => [f.field_code, f.source_column]));
    const c = await req.post(`${API}/reports/${id}/sheets/${s.id}/mapping`, { headers: { "X-CSRF-Token": token }, data: { mappings } });
    expect(c.ok(), await c.text()).toBeTruthy();
  }
  const t2 = Date.now();
  const p = await req.post(`${API}/reports/${id}/process`, { headers: { "X-CSRF-Token": token } });
  expect(p.status(), await p.text()).toBe(202);
  const final = await waitFor(req, id, (s) => ["COMPLETE", "FAILED", "CANCELLED"].includes(s), 1800);
  const t3 = Date.now();
  expect(final).toBe("COMPLETE");
  const r = await (await req.get(`${API}/reports/${id}`)).json();
  return { id, rows: r.rows_processed as number, ingest: (t1 - t0) / 1000, confirm: (t2 - t1) / 1000, process: (t3 - t2) / 1000, total: (t3 - t0) / 1000 };
}

test("landing page, local and live", async ({ page, browser }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1500);
  await shot(page, "landing-1440");
  const live = await browser.newPage({ viewport: VIEWPORTS.desktop });
  await live.emulateMedia({ reducedMotion: "reduce" });
  await live.goto("https://www.truebind.ie/");
  await live.waitForLoadState("networkidle");
  await live.waitForTimeout(1500);
  await live.screenshot({ path: path.join(reviewDir(S), "landing-live-1440.png"), fullPage: true });
  await live.close();
});

test("upload, mapping, report and workbook with timings", async ({ page }) => {
  test.setTimeout(3_600_000);
  await page.setViewportSize(VIEWPORTS.desktop);
  await signUp(page);
  await page.goto("/upload");
  await page.getByText("Bring in a bordereau").first().waitFor();
  await page.waitForLoadState("networkidle");
  await shot(page, "upload-1440");

  // Mapping screen: upload through the UI and stop at the mapping review.
  await page.locator('input[type="file"]').setInputFiles(path.join(DOWNLOADS, "TrueBind_Stress_Test_500_rows.xlsx"));
  await page.waitForURL(/reportId=/, { timeout: 120_000 });
  await page.getByText(/columns mapped automatically/).first().waitFor({ timeout: 300_000 });
  await page.waitForTimeout(800);
  await shot(page, "mapping-1440");

  const times: Record<string, Awaited<ReturnType<typeof processFile>>> = {};
  for (const n of ["500", "10000"]) times[n] = await processFile(page.request, path.join(DOWNLOADS, `TrueBind_Stress_Test_${n}_rows.xlsx`));
  fs.writeFileSync(path.join(reviewDir(S), "timings.json"), JSON.stringify(times, null, 2));
  console.log("TIMINGS", JSON.stringify(times));

  await page.goto(`/reports/${times["500"].id}`);
  await page.getByRole("tab", { name: "Health report" }).waitFor({ timeout: 60_000 });
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(800);
  await shot(page, "report-1440");
  await page.getByRole("tab", { name: "Workbook" }).click();
  await page.getByRole("grid").first().waitFor({ timeout: 120_000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(reviewDir(S), "workbook-1440.png") });
  await page.getByRole("tab", { name: "Review issues" }).click();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(reviewDir(S), "review-1440.png") });
  await page.getByRole("tab", { name: "Trail" }).click();
  await page.getByText("Final verification").waitFor({ timeout: 60_000 });
  await shot(page, "trail-1440");
  await page.goto("/senders");
  await page.waitForLoadState("networkidle");
  await shot(page, "senders-1440");
});
