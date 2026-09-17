import type { MappingState, Severity } from "@/lib/types";
import { MAPPING_STATE_LABEL, MAPPING_STATE_SYMBOL, SEVERITY_LABEL } from "@/lib/constants";
import { Badge, type BadgeTone } from "./Badge";

const MAPPING_TONE: Record<MappingState, BadgeTone> = {
  MAPPED_BY_ALIAS: "success",
  MAPPED_BY_AI: "info",
  MANUAL: "info",
  UNMAPPED: "warning",
};

export function MappingStateBadge({ state }: { state: MappingState }) {
  return (
    <Badge tone={MAPPING_TONE[state]} symbol={MAPPING_STATE_SYMBOL[state]}>
      {MAPPING_STATE_LABEL[state]}
    </Badge>
  );
}

const SEVERITY_TONE: Record<Severity, BadgeTone> = {
  CRITICAL: "error",
  HIGH: "warning",
  MEDIUM: "info",
  INFO: "neutral",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge tone={SEVERITY_TONE[severity]}>{SEVERITY_LABEL[severity]}</Badge>;
}

export function DuplicateMatchBadge({ matchType }: { matchType: "exact_duplicate" | "probable_duplicate" }) {
  return matchType === "exact_duplicate" ? (
    <Badge tone="leakageCertain">Certain duplicate</Badge>
  ) : (
    <Badge tone="leakageProbable">Probable duplicate</Badge>
  );
}

export function GradeBadge({ grade }: { grade: string | null }) {
  if (!grade) return <Badge tone="neutral">Not graded</Badge>;
  const tone: BadgeTone = grade === "5" ? "success" : grade === "1" ? "error" : grade === "4" ? "success" : "warning";
  return <Badge tone={tone}>{grade} / 5</Badge>;
}
