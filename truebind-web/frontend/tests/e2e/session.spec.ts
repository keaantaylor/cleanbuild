import { expect, test, type Page } from "@playwright/test";
import { signUp } from "./helpers";

async function signedIn(page: Page): Promise<number> {
  return page.evaluate(async () => (await fetch("/api/v1/auth/me", { credentials: "include" })).status);
}

// Bug: clicking the TrueBind logo while signed in went to the marketing page,
// which looked signed out. The logo goes to Overview; marketing pages never end a session.
test("the logo always goes to Overview and never ends the session", async ({ page }) => {
  await signUp(page, { name: "Session Tester", org: "Session Org", email: `session-${Date.now()}@example.com` });
  for (const start of ["/overview", "/reports", "/settings"]) {
    await page.goto(start);
    await page.getByRole("link", { name: "TrueBind", exact: false }).first().click();
    await expect(page).toHaveURL(/\/overview$/);
    expect(await signedIn(page), `signed in after clicking the logo on ${start}`).toBe(200);
  }

  for (const path of ["/", "/security", "/demo", "/pricing", "/privacy"]) {
    await page.goto(path);
    expect(await signedIn(page), `still signed in after visiting ${path}`).toBe(200);
  }
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Open TrueBind" }).first()).toBeVisible();
  await page.goto("/login");
  await expect(page).toHaveURL(/\/overview$/);
  await page.goto("/onboarding");
  expect(await signedIn(page)).toBe(200);
});
