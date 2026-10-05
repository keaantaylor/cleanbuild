import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { contrastFailures, TOKENS } from "@/lib/colorContrast";
import { statusMeta } from "@/lib/statusMeta";

const css = readFileSync(fileURLToPath(new URL("../../styles/tokens.css", import.meta.url)), "utf8");

function block(selector: string): string {
  const i = css.indexOf(selector);
  return css.slice(i, css.indexOf("}", i));
}

function value(src: string, name: string): string | undefined {
  return src.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`))?.[1]?.toLowerCase();
}

describe("design tokens", () => {
  it("lib/colorContrast mirrors styles/tokens.css", () => {
    const light = block(`[data-theme="light"]`);
    const dark = block(`[data-theme="dark"]`);
    const sheet = block(`/* Spreadsheet visuals`);
    for (const [k, v] of Object.entries(TOKENS.light)) expect([k, value(light, k)]).toEqual([k, v]);
    for (const [k, v] of Object.entries(TOKENS.dark)) expect([k, value(dark, k)]).toEqual([k, v]);
    for (const [k, v] of Object.entries(TOKENS.sheet)) expect([k, value(sheet, k)]).toEqual([k, v]);
  });

  it("every text/background pair passes WCAG AA", () => {
    expect(contrastFailures()).toEqual([]);
  });

  it("no hex colours outside styles/tokens.css in the new design system", async () => {
    const { readdirSync } = await import("node:fs");
    const dir = fileURLToPath(new URL("../../components/ds/", import.meta.url));
    const offenders = readdirSync(dir)
      .filter((f) => f.endsWith(".css") || f.endsWith(".tsx"))
      .filter((f) => {
        const src = readFileSync(dir + f, "utf8");
        // CSS: any hex colour. TSX: a quoted hex colour (comments like "#113" are fine).
        return f.endsWith(".css") ? /#[0-9a-fA-F]{3,8}\b/.test(src) : /["'`]#[0-9a-fA-F]{3,8}["'`]/.test(src);
      });
    expect(offenders).toEqual([]);
  });
});

describe("statusMeta", () => {
  it("speaks plain English for every engine status", () => {
    expect(statusMeta("FAIL")).toMatchObject({ label: "Breach", tone: "danger" });
    expect(statusMeta("REVIEW")).toMatchObject({ label: "Review", tone: "warning" });
    expect(statusMeta("PASS")).toMatchObject({ label: "Passed", tone: "success" });
    expect(statusMeta("NOT_EVALUABLE")).toMatchObject({ label: "Not assessed", tone: "neutral" });
    expect(statusMeta("NOT_ASSESSED").label).toBe("Not assessed");
    expect(statusMeta("PARTIAL").label).toBe("Partly assessed");
    expect(statusMeta("MAPPED_BY_ALIAS")).toMatchObject({ label: "Matched", tone: "success" });
    expect(statusMeta("MAPPED_BY_AI")).toMatchObject({ label: "Suggested", tone: "warning" });
    expect(statusMeta("MAPPED_BY_MEMORY")).toMatchObject({ label: "Remembered", tone: "success" });
    expect(statusMeta("UNMAPPED")).toMatchObject({ label: "Unmapped", tone: "neutral" });
  });

  it("never shows a raw code for an unknown status", () => {
    expect(statusMeta("SOMETHING_NEW").label).toBe("Something new");
  });
});
