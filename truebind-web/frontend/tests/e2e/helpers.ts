import { expect, type Page } from "@playwright/test";

export const PASSWORD = "correct horse battery staple";

/** Creates an owner account and workspace through the onboarding flow (steps 1 and 2). */
export async function signUp(page: Page, o: { name: string; org: string; email: string }) {
  await page.goto("/onboarding");
  await page.getByLabel("Full name").fill(o.name);
  await page.getByLabel("Work email").fill(o.email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Company name").fill(o.org);
  await page.getByRole("button", { name: "Create my workspace" }).click();
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText(/Tell us about your company/, { timeout: 30_000 });
  const me = await page.evaluate(async () => (await fetch("/api/v1/auth/me", { credentials: "include" })).status);
  expect(me).toBe(200);
}

export async function signOut(page: Page) {
  await page.getByRole("button", { name: /sign out/i }).first().click();
  await expect(page).toHaveURL(/\/login/);
}
