import { expect, test } from "@playwright/test";

import { signUp } from "./helpers";

// P2.7: Settings -> Channels through the real UI and API.

test("an owner sets up e-mail intake and a signed webhook", async ({ page }) => {
  await signUp(page, { name: "Chan Owner", org: "E2E Channels Org", email: `chan-${Date.now()}@example.com` });

  await page.goto("/settings?tab=channels");
  const intake = page.locator("section", { hasText: "Email intake" }).first();
  await expect(intake.getByText("Ready to set up")).toBeVisible();
  await intake.getByRole("button", { name: "Create address" }).click();
  await expect(intake.getByText(/@in\.e2e\.example$/)).toBeVisible();
  await expect(intake.getByText("Live")).toBeVisible();

  await page.getByLabel("Endpoint URL").fill("https://hooks.e2e.example/truebind");
  await page.getByRole("checkbox", { name: "Report failed" }).check();
  await page.getByRole("button", { name: "Add endpoint" }).click();
  const secret = page.getByRole("status").filter({ hasText: "Signing secret" });
  await expect(secret).toContainText("whsec_");
  await secret.getByRole("button", { name: "I have stored it" }).click();
  await expect(page.getByText("whsec_")).toHaveCount(0);
  await expect(page.getByText("https://hooks.e2e.example/truebind")).toBeVisible();
  await page.getByRole("button", { name: "Send test" }).click();
  await expect(page.getByText("Test event queued")).toBeVisible();

  await page.getByLabel("Host", { exact: true }).fill("sftp.partner.example");
  await page.getByLabel("Username").fill("tb");
  await page.getByLabel("Host key fingerprint").fill("not-a-fingerprint");
  await page.getByRole("textbox", { name: "Password" }).fill("pw");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Not saved")).toBeVisible();
});
