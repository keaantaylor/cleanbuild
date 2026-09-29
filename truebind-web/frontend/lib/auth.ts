/** Plain-language messages for the short codes the SSO callback returns in
 * ?sso_error=. The detail is in the organisation's audit trail; the page only
 * says what the person can do about it. */
const SSO_ERRORS: Record<string, string> = {
  invalid_state: "The sign-in took too long or was started in another browser. Please try again.",
  not_configured: "Single sign-on is no longer set up for your organisation. Sign in with your password.",
  invalid_token: "Your identity provider's response could not be verified. Please try again or contact your administrator.",
  no_email: "Your identity provider did not share an e-mail address. Ask your administrator to release the email claim.",
  email_unverified: "Your identity provider says this e-mail address is not verified.",
  domain_mismatch: "Your identity provider signed you in with an e-mail address outside your organisation's domains.",
  not_a_member: "This account is not a member of the organisation that uses this sign-in. Ask an administrator for an invitation.",
  not_provisioned: "Your organisation has not given you access yet. Ask an administrator to invite you.",
};

export function ssoErrorMessage(code: string | null | undefined): string | null {
  if (!code) return null;
  return SSO_ERRORS[code] ?? "Single sign-on failed. Please try again.";
}

/** Only same-site, non-auth paths are valid post-login destinations. */
export function safeNext(next: string | null | undefined, fallback = "/overview"): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login") ? next : fallback;
}

export const ROLE_LABEL: Record<string, string> = {
  OWNER: "Owner", ADMIN: "Admin", ANALYST: "Analyst", VIEWER: "Viewer", SENDER: "Sender",
};

export const ROLE_HELP: Record<string, string> = {
  OWNER: "Everything, including billing and other owners.",
  ADMIN: "Manages members, settings and single sign-on; works the data.",
  ANALYST: "Uploads, maps, processes, reviews and exports.",
  VIEWER: "Read-only access to reports, findings and the audit trail.",
  SENDER: "A coverholder or TPA user: submits files, sees none of your data.",
};

export function hasPermission(permissions: string[] | undefined, permission: string): boolean {
  return (permissions ?? []).includes(permission);
}
