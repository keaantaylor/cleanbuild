/** WCAG relative-luminance contrast checker + the actual token pairs used
 * across the app, checked once at module load (see app/layout.tsx). Keep
 * this list in sync with styles/globals.css (the Nocturne theme tokens) --
 * a text token added there without an entry here is an unverified color,
 * which is exactly what this file exists to prevent. */

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function linearize(c: number): number {
  const v = c / 255;
  return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
}

function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex);
  return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b);
}

export function contrastRatio(fg: string, bg: string): number {
  const l1 = relativeLuminance(fg) + 0.05;
  const l2 = relativeLuminance(bg) + 0.05;
  return Math.max(l1, l2) / Math.min(l1, l2);
}

// The design tokens (styles/globals.css :root). Light only.
const PAIRS: [string, string, string][] = [
  ["text on bg", "#111827", "#F7F8FA"],
  ["text on surface", "#111827", "#FFFFFF"],
  ["muted on bg", "#4B5563", "#F7F8FA"],
  ["muted on surface", "#4B5563", "#FFFFFF"],
  ["faint on bg", "#6B7280", "#F7F8FA"],
  ["faint on surface", "#6B7280", "#FFFFFF"],
  ["primary on surface", "#1F4FD1", "#FFFFFF"],
  ["primary on bg", "#1F4FD1", "#F7F8FA"],
  ["on-primary on primary", "#FFFFFF", "#1F4FD1"],
  ["ok on surface", "#15803D", "#FFFFFF"],
  ["warn on surface", "#B45309", "#FFFFFF"],
  ["err on surface", "#B91C1C", "#FFFFFF"],
  ["err text on err fill", "#9C0006", "#FFC7CE"],
  ["warn text on warn fill", "#7F6000", "#FFF2CC"],
  ["ok text on ok fill", "#375623", "#E2F0D9"],
  ["badge text on badge", "#FFFFFF", "#B91C1C"],
];

export function validateDesignSystemContrast(): void {
  const failures: string[] = [];
  for (const [name, fg, bg] of PAIRS) {
    const ratio = contrastRatio(fg, bg);
    if (ratio < 4.5) {
      failures.push(`${name}: ${ratio.toFixed(2)}:1 (needs >= 4.5:1)`);
    }
  }
  if (failures.length > 0) {
    throw new Error(`Design system contrast validation failed:\n${failures.join("\n")}`);
  }
}

/** Status colours must stay distinct from one another so severity is never
 * carried by a colour another status also uses. */
export function validateDistinctFamilies(): void {
  const families = ["#15803D", "#B45309", "#B91C1C", "#1F4FD1", "#374151"];
  if (new Set(families).size !== families.length) {
    throw new Error("Two status families share a colour value");
  }
}
