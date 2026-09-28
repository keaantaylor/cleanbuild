import { describe, expect, it } from "vitest";

import { provisionalReason, probableDuplicatesValue } from "@/lib/findings";
import type { ReportSummary } from "@/lib/types";

const base = { score_reliable: true, probable_duplicates: 2, not_assessed_checks: [] } as unknown as ReportSummary;
const notAssessed = {
  ...base, score_reliable: false, probable_duplicates: null,
  not_assessed_checks: [{ check: "probable_duplicates", label: "Probable-duplicate check", reason: "3,000,000 candidate row pairs exceed the limit of 2,000,000" }],
} as unknown as ReportSummary;

describe("checks that did not run", () => {
  it("never shows a count for a check that was not assessed", () => {
    expect(probableDuplicatesValue(base)).toBe("2");
    expect(probableDuplicatesValue(notAssessed)).toBe("Not assessed");
  });

  it("says why the grade is provisional", () => {
    expect(provisionalReason(base)).toBeNull();
    expect(provisionalReason(notAssessed)).toBe(
      "The grade is provisional: Probable-duplicate check not assessed (3,000,000 candidate row pairs exceed the limit of 2,000,000).");
    const partial = { ...base, score_reliable: false } as ReportSummary;
    expect(provisionalReason(partial)).toBe("The grade is provisional: at least one sheet was only partly understood.");
  });
});

import { channelStatus } from "@/lib/findings";

describe("channel status wording", () => {
  it("never reads Live unless the channel is active", () => {
    expect(channelStatus("active")).toEqual({ label: "Live", tone: "live" });
    expect(channelStatus("not_set_up").label).toBe("Needs setup");
    expect(channelStatus("not_configured").label).toBe("Not configured on this server");
    expect(channelStatus("planned").label).toBe("Planned");
    expect(channelStatus("anything-else").tone).not.toBe("live");
  });
});
