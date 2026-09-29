import { describe, expect, it } from "vitest";

import { hasPermission, ROLE_HELP, ROLE_LABEL, safeNext, ssoErrorMessage } from "@/lib/auth";
import { isMfaChallenge } from "@/lib/api";
import type { Me, MfaChallenge } from "@/lib/types";

describe("ssoErrorMessage", () => {
  it("explains every code the SSO callback can return, in plain language", () => {
    for (const code of ["invalid_state", "not_configured", "invalid_token", "no_email", "email_unverified",
                        "domain_mismatch", "not_a_member", "not_provisioned"]) {
      const msg = ssoErrorMessage(code);
      expect(msg).toBeTruthy();
      expect(msg).not.toContain(code);
    }
  });
  it("has a safe fallback and ignores absence", () => {
    expect(ssoErrorMessage("something_new")).toMatch(/failed/i);
    expect(ssoErrorMessage(null)).toBeNull();
  });
});

describe("safeNext", () => {
  it("only allows same-site, non-auth paths", () => {
    expect(safeNext("/reports/1")).toBe("/reports/1");
    expect(safeNext("//evil.example")).toBe("/overview");
    expect(safeNext("https://evil.example")).toBe("/overview");
    expect(safeNext("/login?x=1")).toBe("/overview");
    expect(safeNext(null)).toBe("/overview");
  });
});

describe("roles and permissions", () => {
  it("labels and explains every role", () => {
    for (const r of ["OWNER", "ADMIN", "ANALYST", "VIEWER", "SENDER"]) {
      expect(ROLE_LABEL[r]).toBeTruthy();
      expect(ROLE_HELP[r]).toBeTruthy();
    }
  });
  it("checks permissions from /auth/me", () => {
    expect(hasPermission(["data:read", "member:manage"], "member:manage")).toBe(true);
    expect(hasPermission(["data:read"], "member:manage")).toBe(false);
    expect(hasPermission(undefined, "data:read")).toBe(false);
  });
});

describe("isMfaChallenge", () => {
  it("distinguishes a second-factor challenge from a session", () => {
    const challenge: MfaChallenge = { mfa_required: true, mfa_token: "t", methods: ["totp"] };
    const me = { csrf_token: "c" } as Me;
    expect(isMfaChallenge(challenge)).toBe(true);
    expect(isMfaChallenge(me)).toBe(false);
  });
});
