import type { MappingState, Severity } from "./types";

export const MAPPING_STATE_LABEL: Record<MappingState, string> = {
  MAPPED_BY_ALIAS: "Matched",
  MAPPED_BY_AI: "AI-suggested",
  UNMAPPED: "Unmapped",
  MANUAL: "Manually picked",
};

export const MAPPING_STATE_SYMBOL: Record<MappingState, string> = {
  MAPPED_BY_ALIAS: "●",
  MAPPED_BY_AI: "◐",
  UNMAPPED: "▲",
  MANUAL: "◆",
};

export const SEVERITY_LABEL: Record<Severity, string> = {
  CRITICAL: "Critical",
  HIGH: "High",
  MEDIUM: "Medium",
  INFO: "Info",
};

/* Sales contact shown on the demo / Health Check forms and pages.
   NEXT_PUBLIC_CONTACT_PHONE and NEXT_PUBLIC_BOOK_CALL_URL override the
   placeholders (Needs Kealan: real phone number and Calendly/Teams/Zoom link). */
export const CONTACT_EMAIL = "truebind@truebind.ie";
export const CONTACT_PHONE = process.env.NEXT_PUBLIC_CONTACT_PHONE || "";
export const BOOK_CALL_URL = process.env.NEXT_PUBLIC_BOOK_CALL_URL || "https://calendly.com";
