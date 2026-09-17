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
