import ExcelJS from "exceljs";
import { describe, expect, it } from "vitest";
import { csvToXlsx, inferCell, parseCsv } from "@/lib/xlsx";

describe("parseCsv", () => {
  it("handles quotes, embedded commas, newlines, CRLF and a BOM", () => {
    expect(parseCsv('﻿a,b\r\n"x, y","he said ""hi""\nthen left"\r\n')).toEqual([
      ["a", "b"],
      ["x, y", 'he said "hi"\nthen left'],
    ]);
  });
});

describe("inferCell", () => {
  it("stores amounts as numbers and keeps identifiers as text", () => {
    expect(inferCell("1234.50", "paid_indemnity")).toEqual({ kind: "number", value: 1234.5, decimals: 2 });
    expect(inferCell("1234.50", "claim_paid")).toMatchObject({ kind: "number" });
    expect(inferCell("00123", "amount")).toEqual({ kind: "text", value: "00123" });
    expect(inferCell("12345", "claim_reference")).toEqual({ kind: "text", value: "12345" });
    expect(inferCell("12345", "Policy Number")).toEqual({ kind: "text", value: "12345" });
    expect(inferCell("51", "row_number")).toMatchObject({ kind: "number", value: 51 });
    expect(inferCell("123456789012345678", "amount")).toMatchObject({ kind: "text" });
  });
  it("recognises dates and rejects impossible ones", () => {
    expect(inferCell("2026-02-28", "loss_date")).toMatchObject({ kind: "date" });
    expect(inferCell("2026-02-30", "loss_date")).toMatchObject({ kind: "text" });
    expect(inferCell("2026-09-30T14:05:00Z", "created_at")).toMatchObject({ kind: "datetime" });
  });
});

describe("csvToXlsx", () => {
  it("writes a bold frozen header, typed cells and sized columns", async () => {
    const blob = await csvToXlsx("claim_reference,loss_date,paid\n00017,2026-01-05,1200.5\nA-2,2026-01-06,3\n", "Claims");
    const wb = new ExcelJS.Workbook();
    await wb.xlsx.load(await blob.arrayBuffer());
    const ws = wb.getWorksheet("Claims")!;
    expect(ws.getRow(1).font?.bold).toBe(true);
    expect(ws.views[0]).toMatchObject({ state: "frozen", ySplit: 1 });
    expect(ws.getCell("A2").value).toBe("00017");
    expect(ws.getCell("B2").value).toBeInstanceOf(Date);
    expect(ws.getCell("C2").value).toBe(1200.5);
    expect(ws.getCell("C3").numFmt).toBe("#,##0.00");
    expect(ws.getColumn(1).width).toBeGreaterThanOrEqual("claim_reference".length);
  });
});
