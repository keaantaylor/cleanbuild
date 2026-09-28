import { describe, expect, it } from "vitest";

import { decimalMoney, findingWhere, moduleState, provisionalReason, probableDuplicatesValue } from "@/lib/findings";
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

describe("check modules", () => {
  it("never shows not-assessed as a pass", () => {
    expect(moduleState("ASSESSED")).toEqual({ label: "Assessed", tone: "good" });
    expect(moduleState("PARTIAL").label).toBe("Partly assessed");
    expect(moduleState("NOT_ASSESSED")).toEqual({ label: "Not assessed", tone: "warn" });
    expect(moduleState("NOT_RUN").label).toBe("Not run yet");
  });
  it("formats decimal strings exactly, with the currency or saying it is missing", () => {
    expect(decimalMoney("1234567.5", "GBP")).toBe("GBP 1,234,567.50");
    expect(decimalMoney("0.10", "EUR")).toBe("EUR 0.10");
    expect(decimalMoney("-9500.00", "GBP")).toBe("GBP -9,500.00");
    expect(decimalMoney("12", null)).toBe("12.00 (currency not stated)");
    expect(decimalMoney(null, "GBP")).toBe("—");
  });
  it("points at the sheet, row and column, or the whole report", () => {
    expect(findingWhere({ sheet_name: "Claims", row_number: 3, source_column: "Date of Loss" })).toBe("Claims · row 3 · column “Date of Loss”");
    expect(findingWhere({ sheet_name: null, row_number: null, source_column: null })).toBe("Whole report");
  });
});
