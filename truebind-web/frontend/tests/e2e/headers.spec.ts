import { expect, test } from "@playwright/test";

// P10: every page is served with the browser hardening headers, and the API
// behind the proxy keeps its own (no framing, no sniffing).
test("pages and the API are served with security headers", async ({ request }) => {
  const page = await request.get("/login");
  expect(page.status()).toBe(200);
  const h = page.headers();
  expect(h["x-content-type-options"]).toBe("nosniff");
  expect(h["x-frame-options"]).toBe("DENY");
  expect(h["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  expect(h["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(h["strict-transport-security"]).toContain("max-age=");
  expect(h["x-powered-by"]).toBeUndefined();

  const api = await request.get("/api/v1/auth/me");
  expect(api.status()).toBe(401);
  expect(api.headers()["x-content-type-options"]).toBe("nosniff");
});
