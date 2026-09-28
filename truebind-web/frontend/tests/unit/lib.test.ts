import { describe, expect, it } from "vitest";

import { contrastRatio, validateDesignSystemContrast, validateDistinctFamilies } from "@/lib/colorContrast";
import { findingGuide } from "@/lib/findings";
import { formatBytes, formatDuration, formatMoney, formatPct, timeAgo } from "@/lib/formatters";
import { stageIndex, stageLabel, stagesFor } from "@/lib/stages";
import type { Job } from "@/lib/types";

describe("formatters", () => {
  it("renders money in its own currency and never guesses an unknown code", () => {
    expect(formatMoney(1234, "gbp")).toBe("£1,234");
    expect(formatMoney(1234, "EUR")).toBe("€1,234");
    expect(formatMoney(1234, "UNKNOWN")).toBe("1,234");
    expect(formatMoney(1234, "XX1")).toBe("1,234 XX1");
    expect(formatMoney(null, "GBP")).toBe("—");
  });

  it("formats sizes, percentages and durations", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MB");
    expect(formatPct(12.345, 1)).toBe("12.3%");
    expect(formatDuration(0.25)).toBe("250 ms");
    expect(formatDuration(75)).toBe("1 min 15 s");
  });

  it("describes elapsed time relative to an injected clock", () => {
    const now = Date.parse("2026-01-01T12:00:00Z");
    expect(timeAgo("2026-01-01T11:59:50Z", now)).toBe("just now");
    expect(timeAgo("2026-01-01T11:30:00Z", now)).toBe("30 min ago");
    expect(timeAgo("not a date", now)).toBe("not a date");
  });
});

describe("findingGuide", () => {
  it("never reports a not-evaluable check as a pass", () => {
    const g = findingGuide("arithmetic_mismatch", "NOT_EVALUABLE");
    expect(g.certainty).toBe("unknown");
    expect(g.title).toBe("Could not be checked");
  });

  it("has a plain-English guide for known rules and a safe fallback", () => {
    expect(findingGuide("exact_duplicate").title).toBe("Exact resubmission");
    expect(findingGuide("some_new_rule").title).toBe("some new rule");
  });
});

describe("stages", () => {
  const job = (over: Partial<Job>): Job => ({ kind: "PROCESS", status: "RUNNING", stage: "validating", ...over }) as Job;

  it("maps a job to its real stage list", () => {
    expect(stagesFor(job({})).at(-1)?.key).toBe("done");
    expect(stageLabel(job({}))).toBe("Validating");
    expect(stageIndex(job({ status: "SUCCEEDED" }))).toBe(stagesFor(job({})).length - 1);
    expect(stageLabel(job({ status: "QUEUED" }))).toBe("Waiting for the engine");
  });
});

describe("design-system contrast", () => {
  it("computes WCAG ratios", () => {
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 1);
    expect(contrastRatio("#FFFFFF", "#FFFFFF")).toBeCloseTo(1, 5);
  });

  it("every declared token pair meets its contrast floor", () => {
    expect(() => validateDesignSystemContrast()).not.toThrow();
    expect(() => validateDistinctFamilies()).not.toThrow();
  });
});
