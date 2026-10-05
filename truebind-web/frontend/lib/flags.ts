/** Feature flags for the front end. Off means: no nav entry, no marketing
 * mention, and a direct visit shows "Not available yet". Routes stay in the
 * codebase. See docs/design/FRONTEND_PLAN.md for why each is off. */

export const flags = {
  /** Marketing claims that need backend work first (plan gaps G1, G10, G11). */
  claims: {
    unassessedReported: false, // "Unmapped and unassessed data is reported, not hidden" (D1)
    everyRowAccounted: false, // "Every source row is accounted for" (D2)
    hosting: false, // "EU-hosted", "encrypted at rest", "daily backups"
  },
  binders: true, // shown with a Beta chip
  senders: false, // sender memory screens arrive in Session 7
  pricing: false,
  scorecard: false,
  automations: false,
  billing: false,
  sso: false,
  sanctions: false,
} as const;

/** App routes with no nav entry that render "Not available yet" on a direct visit.
 * /inbox, /todo, /duplicates and /alerts join this list when their
 * replacements land (Home, Findings tabs, the notifications panel). */
export const HIDDEN_ROUTES: string[] = [
  ...(flags.scorecard ? [] : ["/scorecard"]),
  ...(flags.automations ? [] : ["/automations"]),
];

export function isHiddenRoute(path: string): boolean {
  return HIDDEN_ROUTES.some((r) => path === r || path.startsWith(r + "/"));
}
