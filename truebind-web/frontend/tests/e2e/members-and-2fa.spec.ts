import { createHmac } from "node:crypto";

import { expect, test } from "@playwright/test";

import { PASSWORD, signOut, signUp } from "./helpers";

// P1.4c: the member + 2FA journey through the real UI and API.

function base32Decode(s: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of s.replace(/=+$/, "").toUpperCase()) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const bytes = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(bytes);
}

/** RFC 6238 TOTP (SHA-1, 30 s, 6 digits) for the step `offset` steps from now. */
function totp(secret: string, offset = 0): string {
  const step = Math.floor(Date.now() / 1000 / 30) + offset;
  const msg = Buffer.alloc(8);
  msg.writeBigUInt64BE(BigInt(step));
  const h = createHmac("sha1", base32Decode(secret)).update(msg).digest();
  const o = h[h.length - 1] & 0xf;
  const n = ((h[o] & 0x7f) << 24) | (h[o + 1] << 16) | (h[o + 2] << 8) | h[o + 3];
  return String(n % 1_000_000).padStart(6, "0");
}

test("owner invites an analyst, then protects their own account with 2FA", async ({ page, browser }) => {
  const owner = `owner-${Date.now()}@example.com`;
  await signUp(page, { name: "Olive Owner", org: "E2E Members Org", email: owner });

  // ---- invite an analyst
  await page.goto("/settings?tab=members");
  const analyst = `analyst-${Date.now()}@example.com`;
  await page.getByLabel("Work email").fill(analyst);
  await page.getByLabel("Role", { exact: true }).selectOption("ANALYST");
  await page.getByRole("button", { name: "Create invitation" }).click();
  const link = (await page.getByTestId("invite-link").innerText()).trim();
  expect(link).toContain("/invite?token=");

  const other = await browser.newContext();
  const invitee = await other.newPage();
  await invitee.goto(link);
  await invitee.getByLabel("Your name").fill("Ann Analyst");
  await invitee.getByLabel("Password").fill(PASSWORD);
  await invitee.getByRole("button", { name: "Join workspace" }).click();
  await expect(invitee).toHaveURL(/\/overview/, { timeout: 30_000 });
  const me = await invitee.evaluate(async () => (await fetch("/api/v1/auth/me", { credentials: "include" })).json());
  expect(me.role).toBe("ANALYST");
  await other.close();

  await page.reload();
  await expect(page.getByRole("cell", { name: new RegExp(analyst) })).toBeVisible();

  // ---- turn on 2FA for the owner
  await page.goto("/settings?tab=security");
  await page.getByRole("button", { name: "Set up two-step verification" }).click();
  const secret = (await page.getByTestId("totp-secret").innerText()).trim();
  await page.getByLabel(/Enter the 6-digit code/).fill(totp(secret));
  await page.getByRole("button", { name: "Turn on" }).click();
  await expect(page.getByTestId("recovery-codes").locator("li")).toHaveCount(10);
  await page.getByRole("button", { name: "I have saved them" }).click();

  // ---- sign out, sign back in: the password alone is not enough
  await signOut(page);
  await page.getByLabel("Work email").fill(owner);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Two-step verification" })).toBeVisible();
  await page.getByLabel("Authentication code").fill("000000");
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByText("The code is not valid.")).toBeVisible();
  await page.getByLabel("Authentication code").fill(totp(secret, 1)); // next step: not the one used to enable
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page).toHaveURL(/\/overview/, { timeout: 30_000 });
});
