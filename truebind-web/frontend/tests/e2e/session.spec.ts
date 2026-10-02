import { expect, test } from "@playwright/test";
import { signUp } from "./helpers";

// Bug: clicking the TrueBind logo while signed in went to the marketing page,
// which looked signed out. The logo goes to Overview; marketing pages never end a session.
test("the logo goes to Overview and marketing pages keep the session", async ({ page }) => {
  await signUp(page, { name: "Session Tester", org: "Session Org", email: `session-${Date.now()}@example.com` });
  await page.goto("/overview");
  await page.getByRole("link", { name: /TrueBind/ }).first().click();
  await expect(page).toHaveURL(/\/overview$/);

  for (const path of ["/", "/security", "/sample-report", "/privacy"]) {
    await page.goto(path);
    const status = await page.evaluate(async () => (await fetch("/api/v1/auth/me", { credentials: "include" })).status);
    expect(status, `still signed in after visiting ${path}`).toBe(200);
  }
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Open TrueBind" }).first()).toBeVisible();
  await page.goto("/login");
  await expect(page).toHaveURL(/\/overview$/);
});
