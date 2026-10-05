import { test } from "@playwright/test";
import { reviewDir, shoot, signUp, VIEWPORTS } from "./helpers";

const S = "session-0";

for (const theme of ["light", "dark"] as const) {
  test(`design system, ${theme}`, async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await page.goto(`/design-system?theme=${theme}`);
    await page.getByRole("heading", { name: "Colour" }).waitFor();
    await shoot(page, S, `design-system-${theme}-1440`);
    await page.setViewportSize(VIEWPORTS.phone);
    await shoot(page, S, `design-system-${theme}-390`, true);
  });
}

test("app shell on Home", async ({ page }) => {
  await signUp(page);
  await page.setViewportSize(VIEWPORTS.desktop);
  await page.goto("/overview");
  await page.getByRole("navigation", { name: "Main" }).first().waitFor();
  await page.waitForLoadState("networkidle");
  await shoot(page, S, "overview-1440");
  await page.keyboard.press("Control+k");
  await page.getByRole("combobox", { name: "Search" }).waitFor();
  await page.screenshot({ path: `${reviewDir(S)}/command-palette-1440.png` });
  await page.keyboard.press("Escape");
  await page.setViewportSize(VIEWPORTS.phone);
  await page.waitForTimeout(300);
  await shoot(page, S, "overview-390", true);
});

test("marketing shell", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: `${reviewDir(S)}/marketing-shell-1440.png` });
  await page.setViewportSize(VIEWPORTS.phone);
  await shoot(page, S, "marketing-shell-390", true);
});
