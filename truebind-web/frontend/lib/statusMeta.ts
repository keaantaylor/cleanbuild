/** Every status word the UI shows goes through here, so a system code never
 * reaches the screen on its own. Tone picks the colour family. */

export type Tone = "danger" | "warning" | "success" | "neutral" | "brand";

export interface StatusMeta {
  label: string;
  tone: Tone;
}

const META: Record<string, StatusMeta> = {
  FAIL: { label: "Breach", tone: "danger" },
  REVIEW: { label: "Review", tone: "warning" },
  PASS: { label: "Passed", tone: "success" },
  NOT_ASSESSED: { label: "Not assessed", tone: "neutral" },
  NOT_EVALUABLE: { label: "Not assessed", tone: "neutral" },
  PARTIAL: { label: "Partly assessed", tone: "neutral" },
  MAPPED_BY_ALIAS: { label: "Matched", tone: "success" },
  MAPPED_BY_MEMORY: { label: "Remembered", tone: "success" },
  MAPPED_BY_AI: { label: "Suggested", tone: "warning" },
  UNMAPPED: { label: "Unmapped", tone: "neutral" },
  // Verdict states (lib/verdict.ts)
  CLEAN: { label: "Clean", tone: "success" },
  ISSUES_OPEN: { label: "Issues open", tone: "danger" },
  INCOMPLETE: { label: "Incomplete", tone: "warning" },
  PROCESSING: { label: "Processing", tone: "brand" },
  FAILED: { label: "Failed", tone: "danger" },
};

/** "SOMETHING_NEW" → "Something new": an unknown code still reads as words. */
function humanise(code: string): string {
  const words = code.toLowerCase().replace(/_/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function statusMeta(code: string | null | undefined): StatusMeta {
  if (!code) return { label: "Unknown", tone: "neutral" };
  return META[code.toUpperCase()] ?? { label: humanise(code), tone: "neutral" };
}
