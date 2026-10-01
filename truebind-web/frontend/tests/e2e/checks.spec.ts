import path from "node:path";

import { expect, test } from "@playwright/test";

import { signUp } from "./helpers";

// P3: binder compliance through the real UI -- add a binder, process the golden
// binder file, assign the binder, read and decide a finding.
const DIRTY = path.resolve(__dirname, "../../../../fixtures/golden/binder/dirty.xlsx");

test("an analyst checks a bordereau against its binder and dismisses a finding with a reason", async ({ page }) => {
  await signUp(page, { name: "Binder Owner", org: "E2E Binder Org", email: `binder-${Date.now()}@example.com` });

  await page.goto("/settings?tab=binders");
  const form = page.getByRole("form", { name: "Add a binder" });
  await form.getByLabel("Name").fill("E2E Binder 2024-25");
  await form.getByLabel("Inception date").fill("2024-03-01");
  await form.getByLabel("Expiry date (inclusive)").fill("2025-02-28");
  await form.getByLabel("Permitted settlement currencies").fill("GBP, EUR");
  await form.getByLabel(/Claims settlement authority/).fill("50000");
  await form.getByRole("button", { name: "Add binder" }).click();
  await expect(page.getByRole("cell", { name: /E2E Binder 2024-25/ })).toBeVisible();
  await expect(page.getByRole("cell", { name: "GBP 50,000.00" })).toBeVisible();

  await page.goto("/upload");
  await page.setInputFiles("input[type=file]", DIRTY);
  const confirmAll = page.getByRole("button", { name: /Confirm all as proposed/ });
  await expect(confirmAll).toBeVisible({ timeout: 120_000 });
  await confirmAll.click();
  await page.getByRole("button", { name: "Produce health report" }).click();
  await expect(page).toHaveURL(/\/reports\/[^/]+$/, { timeout: 60_000 });
  await expect(page.getByRole("button", { name: "Audit pack" })).toBeVisible({ timeout: 180_000 });
  await page.getByRole("tab", { name: "Other checks & evidence" }).click();

  const binderCard = page.locator("section", { hasText: "Binder compliance" }).first();
  await expect(binderCard.getByText(/No binder is assigned/).first()).toBeVisible();
  await binderCard.getByLabel("Binder this bordereau is reported under").selectOption({ index: 1 });
  const list = page.getByRole("list", { name: "Binder compliance findings" });
  await expect(list.getByRole("button", { name: /Loss date outside the binder period/ }).first()).toBeVisible();
  await expect(list.getByRole("button", { name: /Loss date is ambiguous/ })).toHaveCount(2);
  await expect(list.getByRole("button", { name: /Currency not permitted/ })).toHaveCount(2);

  const item = list.locator("li").filter({ has: page.getByRole("button", { name: /Claims · row 3 ·/ }) });
  await item.getByRole("button", { name: /Claims · row 3 ·/ }).click();
  await expect(page.getByText(/is before the binder incepted on 01 March 2024/)).toBeVisible();
  await expect(item.getByRole("button", { name: "Dismiss" })).toBeDisabled();
  await item.getByLabel(/Note/).fill("Late-notified claim agreed by the insurer");
  await item.getByRole("button", { name: "Dismiss" }).click();
  await expect(item.getByText(/Late-notified claim agreed by the insurer/)).toBeVisible();
  await expect(item.getByText("dismissed", { exact: true })).toBeVisible();
  await expect(item.getByText(/^Dismissed by /)).toBeVisible();
});
