import path from "node:path";

import { expect, test } from "@playwright/test";

// P8: a coverholder (SENDER) is invited, lands in the sender portal (not the
// provider's workspace), pre-flights a bordereau and sends it.
const DIRTY = path.resolve(__dirname, "../../../../fixtures/golden/leakage/dirty.xlsx");
const PASSWORD = "correct horse battery staple";

test("a sender pre-flights a bordereau and sends it to the organisation", async ({ page, browser }) => {
  await page.goto("/login?mode=signup");
  await page.getByLabel("Your name").fill("Portal Owner");
  await page.getByLabel("Organisation").fill("E2E Portal Org");
  await page.getByLabel("Work e-mail").fill(`portal-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).not.toHaveURL(/\/login/, { timeout: 30_000 });

  const token = await page.evaluate(async () => {
    const r = await fetch("/api/v1/org/invitations", {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": sessionStorage.getItem("tb_csrf") ?? "" },
      body: JSON.stringify({ email: `tpa-${Date.now()}@partner.example`, role: "SENDER" }),
    });
    return (await r.json()).accept_token as string;
  });
  expect(token).toBeTruthy();

  const ctx = await browser.newContext();
  const tpa = await ctx.newPage();
  await tpa.goto(`/invite?token=${encodeURIComponent(token)}`);
  await tpa.getByLabel("Your name").fill("TPA User");
  await tpa.getByLabel("Password").fill(PASSWORD);
  await tpa.getByRole("button", { name: "Join workspace" }).click();
  await expect(tpa).toHaveURL(/\/sender$/, { timeout: 30_000 });
  await tpa.goto("/overview");
  await expect(tpa).toHaveURL(/\/sender$/, { timeout: 30_000 }); // never the provider's workspace

  await tpa.getByLabel(/Bordereau file/).setInputFiles(DIRTY);
  await tpa.getByRole("button", { name: "Check file" }).click();
  await expect(tpa.getByText("Needs attention")).toBeVisible({ timeout: 60_000 });
  await expect(tpa.getByRole("table", { name: /Sheets and the columns recognised/ })).toBeVisible();
  await tpa.getByRole("button", { name: /Send to E2E Portal Org/ }).click();
  await expect(tpa.getByText(/was sent to E2E Portal Org/)).toBeVisible({ timeout: 30_000 });
  await expect(tpa.getByRole("table", { name: /Your submissions/ }).getByText("dirty.xlsx")).toBeVisible();
  await ctx.close();

  await page.goto("/inbox");
  await expect(page.locator("main")).toContainText("dirty.xlsx", { timeout: 30_000 });
});
