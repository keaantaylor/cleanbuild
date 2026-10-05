import path from "node:path";

import { expect, test } from "@playwright/test";

import { signUp } from "./helpers";

// The workbook is the review surface: virtualised, keyboard-driven, issue cells
// reachable from the review queue, every state named in words.
const FIXTURE = path.resolve(__dirname, "../../../../bordereaux/data/synthetic/test_boundary_cases.xlsx");

test("workbook grid: virtualised, searchable, keyboard navigation, issue to cell", async ({ page }) => {
  await signUp(page, { name: "Grid Tester", org: "Grid Org", email: `grid-${Date.now()}@example.com` });
  await page.goto("/upload");
  await page.setInputFiles("input[type=file]", FIXTURE);
  const confirmAll = page.getByRole("button", { name: /Confirm all as proposed/ });
  await expect(confirmAll).toBeVisible({ timeout: 120_000 });
  await confirmAll.click();
  await page.getByRole("button", { name: "Produce health report" }).click();
  await expect(page).toHaveURL(/\/reports\/[^/]+$/, { timeout: 60_000 });

  const grid = page.getByRole("grid");
  await expect(grid).toBeVisible({ timeout: 180_000 });
  await expect(page.getByText("Requires reconciliation").first()).toBeVisible(); // the legend names every state
  // Only the cells in view are in the DOM, not the whole sheet.
  await expect(grid.getByRole("gridcell").first()).toBeVisible({ timeout: 30_000 });
  expect(await grid.getByRole("gridcell").count()).toBeLessThan(1500);

  // Keyboard: the active cell moves and the inspector follows.
  await grid.focus();
  await page.keyboard.press("Control+Home");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowRight");
  await expect(page.getByLabel("Cell inspector")).toContainText("!B2");

  // Next issue lands on a flagged cell and the inspector says what is wrong, in words.
  await page.getByRole("button", { name: "Next issue" }).click();
  await expect(page.getByLabel("Cell inspector")).toContainText(/Requires reconciliation|Undetermined/);
  await expect(page.getByLabel("Cell inspector")).toContainText(/ v\d+\.\d+/); // the rule and its version

  // From the review queue, "Show in workbook" opens the exact cell.
  await page.getByRole("tab", { name: "Review issues" }).click();
  const show = page.getByRole("button", { name: "Show in workbook" });
  await expect(show).toBeVisible({ timeout: 30_000 });
  const cellText = (await page.locator("dd").first().innerText()).split(" ")[0]; // e.g. Claims!I15
  await show.click();
  await expect(grid).toBeVisible();
  await expect(page.getByLabel("Cell inspector")).toContainText(cellText);
});
