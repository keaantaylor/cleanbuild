import { expect, type Page } from "@playwright/test";
import path from "node:path";

export const VIEWPORTS = { desktop: { width: 1440, height: 900 }, phone: { width: 390, height: 844 } } as const;

export function reviewDir(session: string): string {
  return path.resolve(__dirname, "../../../../docs/design/review", session);
}

/** Saves a full-page screenshot and, on phones, fails if the page scrolls sideways. */
export async function shoot(page: Page, session: string, name: string, phone = false): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  if (phone) {
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width, `${name} scrolls sideways at 390px`).toBeLessThanOrEqual(390);
  }
  await page.screenshot({ path: path.join(reviewDir(session), `${name}.png`), fullPage: true });
}

/** A fresh workspace for screenshots of signed-in pages (local API only). */
export async function signUp(page: Page): Promise<void> {
  const api = process.env.VISUAL_API_URL ?? "http://localhost:8000/api/v1";
  const stamp = Date.now();
  const res = await page.request.post(`${api}/auth/signup`, {
    data: { email: `review+${stamp}@example.com`, password: `Review-${stamp}-pass!`, display_name: "Molly Byrne", organisation: "Sample Workspace" },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
}
