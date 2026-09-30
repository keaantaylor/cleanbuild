import path from "node:path";

import { expect, test } from "@playwright/test";

import { signOut, signUp } from "./helpers";

// The golden regression, driven through the real UI: the 320-row / 10-sheet
// boundary fixture must report its answer-key totals end to end.
const FIXTURE = path.resolve(__dirname, "../../../../bordereaux/data/synthetic/test_boundary_cases.xlsx");

test("sign up, upload the golden workbook, confirm mapping, read the report, sign out", async ({ page, request }) => {
  await page.goto("/upload");
  await expect(page).toHaveURL(/\/login/);

  await page.goto("/login?mode=signup");
  await expect(page).toHaveURL(/\/onboarding/);
  await signUp(page, { name: "E2E Tester", org: "E2E Org", email: `e2e-${Date.now()}@example.com` });

  await page.goto("/upload");
  await page.setInputFiles("input[type=file]", FIXTURE);

  const confirmAll = page.getByRole("button", { name: /Confirm all as proposed/ });
  await expect(confirmAll).toBeVisible({ timeout: 120_000 });
  await confirmAll.click();
  const produce = page.getByRole("button", { name: "Produce health report" });
  await expect(produce).toBeVisible({ timeout: 60_000 });
  await produce.click();

  await expect(page).toHaveURL(/\/reports\/[^/]+$/, { timeout: 60_000 });
  await expect(page.getByRole("button", { name: "Audit pack" })).toBeVisible({ timeout: 180_000 });
  const reportId = page.url().split("/").pop()!;

  // Answer-key totals, read back through the same API the page uses.
  const summary = await page.evaluate(async (id) => {
    const r = await fetch(`/api/v1/reports/${id}/summary`, { credentials: "include" });
    return r.json();
  }, reportId);
  const s = summary.summary;
  expect(s.arithmetic_mismatches).toBe(38);
  expect(s.arithmetic_not_evaluable).toBe(0);

  await page.goto(`/exceptions?reportId=${reportId}`);
  await expect(page.locator("main")).toContainText(/arithmetic/i);

  await signOut(page);
  const after = await request.get(`/api/v1/reports/${reportId}`);
  expect(after.status()).toBe(401);
});
