"use client";

import { saveBlob } from "./exports";

/* Minimal PDF writer (PDF 1.4, Helvetica, A4) used for the Health Check
   document. Everything it prints comes from the report's real summary. */

function save(blob: Blob, filename: string) {
  saveBlob(blob, filename);
}

/** Result colours, shared with the screen and the annotated workbook (see lib/severity.ts). */
export type PdfTone = "err" | "warn" | "ok" | "muted";
const TONE_RGB: Record<PdfTone, { fill: string; text: string }> = {
  err: { fill: "1 0.78 0.808", text: "0.612 0 0.024" }, // FFC7CE / 9C0006
  warn: { fill: "1 0.949 0.8", text: "0.498 0.376 0" }, // FFF2CC / 7F6000
  ok: { fill: "0.886 0.941 0.851", text: "0.216 0.337 0.137" }, // E2F0D9 / 375623
  muted: { fill: "0.906 0.902 0.902", text: "0.227 0.227 0.227" }, // E7E6E6 / 3A3A3A
};

export type PdfBlock =
  | { kind: "callout"; text: string; sub?: string; tone: PdfTone }
  | { kind: "title"; text: string }
  | { kind: "kicker"; text: string }
  | { kind: "heading"; text: string }
  | { kind: "text"; text: string }
  | { kind: "muted"; text: string }
  | { kind: "row"; cells: string[]; widths: number[]; bold?: boolean; tones?: (PdfTone | undefined)[] }
  | { kind: "rule" }
  | { kind: "space"; h?: number };

/** Minimal PDF writer (PDF 1.4, Helvetica, A4). Enough for a real, openable report. */
export function downloadPdf(filename: string, blocks: PdfBlock[], footer: string) {
  const W = 595,
    H = 842,
    M = 56;
  const pages: string[][] = [[]];
  let y = H - M;
  const winAnsi = (s: string) =>
    s
      .replace(/[‘’]/g, "'")
      .replace(/[“”]/g, '"')
      .replace(/[–—]/g, "-")
      .replace(/…/g, "...")
      .replace(/→/g, "->")
      .replace(/←/g, "<-")
      .replace(/≠/g, "!=")
      .replace(/≤/g, "<=")
      .replace(/Δ/g, "delta ")
      .replace(/−/g, "-")
      .replace(/·/g, "·")
      .replace(/[^\x20-\x7e -ÿ£€]/g, "");
  const esc = (s: string) => winAnsi(s).replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
  const enc = (s: string) => esc(s).replace(/€/g, "\\200");
  const cur = () => pages[pages.length - 1];
  const need = (h: number) => {
    if (y - h < M + 30) {
      pages.push([]);
      y = H - M;
    }
  };
  const text = (x: number, size: number, font: "F1" | "F2", s: string, gray: number | string = 0.1) => {
    const colour = typeof gray === "number" ? `${gray} g` : `${gray} rg`;
    cur().push(`${colour} BT /${font} ${size} Tf ${x} ${y} Td (${enc(s)}) Tj ET`);
  };
  const wrap = (s: string, size: number, width: number) => {
    const max = Math.floor(width / (size * 0.5));
    const out: string[] = [];
    let line = "";
    for (const w of s.split(" ")) {
      if ((line + " " + w).trim().length > max) {
        out.push(line);
        line = w;
      } else line = (line + " " + w).trim();
    }
    if (line) out.push(line);
    return out;
  };

  for (const b of blocks) {
    if (b.kind === "space") {
      y -= b.h ?? 10;
      continue;
    }
    if (b.kind === "rule") {
      need(12);
      y -= 6;
      cur().push(`0.8 G 0.5 w ${M} ${y} m ${W - M} ${y} l S`);
      y -= 18;
      continue;
    }
    if (b.kind === "callout") {
      const lines = wrap(b.text, 15, W - 2 * M - 24);
      const sub = b.sub ? wrap(b.sub, 9.5, W - 2 * M - 24) : [];
      const h = 18 + lines.length * 19 + sub.length * 13;
      need(h + 8);
      const c = TONE_RGB[b.tone];
      cur().push(`${c.fill} rg ${M} ${y - h + 12} ${W - 2 * M} ${h} re f`);
      y -= 8;
      for (const line of lines) {
        text(M + 12, 15, "F2", line, c.text);
        y -= 19;
      }
      for (const line of sub) {
        text(M + 12, 9.5, "F1", line, c.text);
        y -= 13;
      }
      y -= 14;
      continue;
    }
    if (b.kind === "row") {
      need(16);
      let x = M;
      b.cells.forEach((c, i) => {
        const w = b.widths[i] * (W - 2 * M);
        const max = Math.floor(w / (9 * 0.5)) - 1;
        const tone = b.tones?.[i];
        text(x, 9, b.bold || tone ? "F2" : "F1", c.length > max ? c.slice(0, max - 1) + "..." : c, tone ? TONE_RGB[tone].text : b.bold ? 0.4 : 0.1);
        x += w;
      });
      y -= 16;
      continue;
    }
    const style = {
      title: { size: 18, font: "F2" as const, gray: 0.1, lead: 23 },
      kicker: { size: 8.5, font: "F2" as const, gray: 0.38, lead: 14 },
      heading: { size: 11.5, font: "F2" as const, gray: 0.1, lead: 17 },
      text: { size: 10, font: "F1" as const, gray: 0.15, lead: 14 },
      muted: { size: 9, font: "F1" as const, gray: 0.4, lead: 13 },
    }[b.kind];
    for (const line of wrap(b.text, style.size, W - 2 * M)) {
      need(style.lead);
      text(M, style.size, style.font, line, style.gray);
      y -= style.lead;
    }
  }

  const objs: string[] = [];
  objs.push("<< /Type /Catalog /Pages 2 0 R >>");
  objs.push(""); // pages, filled below
  objs.push("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>");
  objs.push("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>");
  const kids: number[] = [];
  pages.forEach((ops, i) => {
    const foot = `0.45 g BT /F1 8 Tf ${M} 34 Td (${enc(footer)}) Tj ET 0.45 g BT /F1 8 Tf ${W - M - 60} 34 Td (Page ${i + 1} of ${pages.length}) Tj ET`;
    const stream = ops.join("\n") + "\n" + foot;
    objs.push(`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
    const contentId = objs.length;
    objs.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${W} ${H}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents ${contentId} 0 R >>`);
    kids.push(objs.length);
  });
  objs[1] = `<< /Type /Pages /Kids [${kids.map((k) => `${k} 0 R`).join(" ")}] /Count ${kids.length} >>`;

  // Build with byte offsets; content is Latin-1 so one char = one byte.
  let out = "%PDF-1.4\n%âãÏÓ\n";
  const offsets: number[] = [];
  objs.forEach((o, i) => {
    offsets.push(out.length);
    out += `${i + 1} 0 obj\n${o}\nendobj\n`;
  });
  const xref = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n`;
  offsets.forEach((o) => (out += String(o).padStart(10, "0") + " 00000 n \n"));
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  const bytes = new Uint8Array(out.length);
  for (let i = 0; i < out.length; i++) bytes[i] = out.charCodeAt(i) & 0xff;
  save(new Blob([bytes], { type: "application/pdf" }), filename);
}
