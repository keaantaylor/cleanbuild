import { describe, expect, it } from "vitest";
import { filenameFromDisposition } from "../../lib/exports";
import { viewRow, VIEW_HEAD } from "../../lib/exceptions-view";
import type { ExceptionRow } from "../../lib/types";

describe("filenameFromDisposition", () => {
  it("reads the quoted filename the backend sends", () => {
    expect(filenameFromDisposition('attachment; filename="TrueBind_Health_Report_Acme_2026-10-12.xlsx"', "x.xlsx"))
      .toBe("TrueBind_Health_Report_Acme_2026-10-12.xlsx");
  });
  it("prefers RFC 5987 filename*", () => {
    expect(filenameFromDisposition("attachment; filename=\"a.xlsx\"; filename*=UTF-8''R%C3%A9sum%C3%A9.xlsx", "x.xlsx")).toBe("Résumé.xlsx");
  });
  it("falls back when the header is missing or empty", () => {
    expect(filenameFromDisposition(null, "fallback.xlsx")).toBe("fallback.xlsx");
    expect(filenameFromDisposition("attachment", "fallback.xlsx")).toBe("fallback.xlsx");
  });
});

describe("viewRow", () => {
  const base: ExceptionRow = {
    claim_row_id: "c", claim_reference: "CLM-1", sheet_name: "Claims", row_index: 0, source_row_number: 14, currency: "GBP",
    rule: "arithmetic_mismatch", review_status: "resolved", assignee: "Sam", note: null, amount: 1500, check_type: "ARITHMETIC",
    status: "FAIL", severity: "HIGH", message: "raw", validation_result_id: "v", cell: "I14", source_column: "Total Incurred",
    sentence: "Total incurred does not reconcile: 1,500 but 1,000 + 400 = 1,400.", owner: "sender",
  };
  it("uses the same words as the Health Report", () => {
    const row = viewRow(base, { arithmetic_mismatch: "Total incurred does not reconcile" });
    expect(row).toHaveLength(VIEW_HEAD.length);
    expect(row.slice(0, 3)).toEqual(["Error", "High", "Total incurred does not reconcile"]);
    expect(row[VIEW_HEAD.indexOf("Status")]).toBe("Resolved");
    expect(row[VIEW_HEAD.indexOf("Who fixes")]).toBe("Sender");
  });
  it("says Couldn't check, never a blank, for findings that couldn't be evaluated", () => {
    expect(viewRow({ ...base, status: "NOT_EVALUABLE", review_status: null }, {})[0]).toBe("Couldn't check");
  });
});
