/** WCAG relative-luminance contrast checker + the actual token pairs used
 * across the app, checked once at module load (see app/layout.tsx). Keep
 * this list in sync with styles/variables.css -- a token added there
 * without an entry here is an unverified color, which is exactly what
 * this file exists to prevent. */

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

const LIGHT_PAIRS: [string, string, string][] = [
  ["text-primary on bg-primary", "#111827", "#FFFFFF"],
  ["text-secondary on bg-primary", "#6B7280", "#FFFFFF"],
  ["text-tertiary on bg-primary", "#69737F", "#FFFFFF"],
  ["text-tertiary on bg-secondary", "#69737F", "#F9FAFB"],
  ["primary on white", "#2E3FE0", "#FFFFFF"],
  ["success on white", "#15803D", "#FFFFFF"],
  ["success on success-bg", "#15803D", "#DCFCE7"],
  ["warning on white", "#B45309", "#FFFFFF"],
  ["warning on warning-bg", "#B45309", "#FEF3C7"],
  ["error on white", "#B91C1C", "#FFFFFF"],
  ["error on error-bg", "#B91C1C", "#FEE2E2"],
  ["info on white", "#0369A1", "#FFFFFF"],
  ["info on info-bg", "#0369A1", "#E0F2FE"],
  ["not-evaluable on white", "#7C3AED", "#FFFFFF"],
  ["not-evaluable on not-evaluable-bg", "#7C3AED", "#EDE9FE"],
  ["leakage-possible on its bg", "#78350F", "#FFFBEB"],
  ["leakage-probable on its bg", "#92400E", "#FEF3C7"],
  ["leakage-certain on its bg", "#B91C1C", "#FEE2E2"],
  ["sanctions on sanctions-bg", "#FFFFFF", "#000000"],
  ["grade-5 on white", "#15803D", "#FFFFFF"],
  ["grade-4 on white", "#4D7C0F", "#FFFFFF"],
  ["grade-3 on white", "#7E7407", "#FFFFFF"],
  ["grade-2 on white", "#B85B0A", "#FFFFFF"],
  ["grade-1 on white", "#DC2626", "#FFFFFF"],

  // Marketing site (styles/marketing.css) -- a separate, light-mode-only
  // palette (see that file's header comment for why), but validated the
  // same way as everything else here.
  ["mkt-ink on mkt-surface", "#0B0F19", "#FFFFFF"],
  ["mkt-ink-secondary on mkt-surface", "#4B5468", "#FFFFFF"],
  ["mkt-accent on mkt-surface", "#2E3FE0", "#FFFFFF"],
  ["mkt-accent on mkt-accent-bg", "#2E3FE0", "#EEF0FD"],
  ["mkt-ink on mkt-surface-sunken", "#0B0F19", "#F5F6FA"],
  ["mkt-ink-secondary on mkt-surface-sunken", "#4B5468", "#F5F6FA"],
  ["mkt-surface on mkt-ink (dark hero)", "#FFFFFF", "#0B0F19"],
  ["mkt-ink-secondary-light on mkt-ink (dark hero)", "#CBD1E0", "#0B0F19"],
  ["mkt trust-section eyebrow on mkt-ink", "#A9B4FF", "#0B0F19"],
  ["mkt trust-section muted on mkt-ink", "#8891AE", "#0B0F19"],
];

const DARK_PAIRS: [string, string, string][] = [
  ["text-primary-dark on bg-primary-dark", "#F8FAFC", "#0F172A"],
  ["text-secondary-dark on bg-primary-dark", "#CBD5E1", "#0F172A"],
  ["text-tertiary-dark on bg-primary-dark", "#94A3B8", "#0F172A"],
  ["success-dark on its bg", "#4ADE80", "#14532D"],
  ["warning-dark on its bg", "#FBBF24", "#78350F"],
  ["error-dark on its bg", "#FCA5A5", "#7F1D1D"],
  ["info-dark on its bg", "#7DD3FC", "#0C4A6E"],
  ["not-evaluable-dark on its bg", "#C4B5FD", "#4C1D95"],
  ["leakage-possible-dark on its bg", "#FDE68A", "#78350F"],
  ["leakage-probable-dark on its bg", "#FCD34D", "#78350F"],
  ["leakage-certain-dark on its bg", "#FCA5A5", "#7F1D1D"],
  ["grade-5-dark on bg", "#4ADE80", "#0F172A"],
  ["grade-4-dark on bg", "#A3E635", "#0F172A"],
  ["grade-3-dark on bg", "#FBDE23", "#0F172A"],
  ["grade-2-dark on bg", "#FB923C", "#0F172A"],
  ["grade-1-dark on bg", "#F87171", "#0F172A"],
];

export function validateDesignSystemContrast(): void {
  const failures: string[] = [];
  for (const [name, fg, bg] of [...LIGHT_PAIRS, ...DARK_PAIRS]) {
    const ratio = contrastRatio(fg, bg);
    if (ratio < 4.5) {
      failures.push(`${name}: ${ratio.toFixed(2)}:1 (needs >= 4.5:1)`);
    }
  }
  if (failures.length > 0) {
    throw new Error(`Design system contrast validation failed:\n${failures.join("\n")}`);
  }
}

/** Also asserts not-evaluable and sanctions never collide with any other
 * family's hex value -- a distinct hue family is only meaningful if the
 * values are actually distinct. */
export function validateDistinctFamilies(): void {
  const reserved = new Set(["#7C3AED", "#C4B5FD", "#FFFFFF", "#000000"]);
  const other = ["#15803D", "#4ADE80", "#B45309", "#FBBF24", "#DC2626", "#FCA5A5", "#0369A1", "#7DD3FC"];
  const overlap = other.filter((c) => reserved.has(c));
  if (overlap.length > 0) {
    throw new Error(`not-evaluable/sanctions colors collide with another status family: ${overlap.join(", ")}`);
  }
}
