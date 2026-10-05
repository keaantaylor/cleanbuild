/** WCAG contrast checks for every text/background pair the design system
 * uses, run once at module load (app/layout.tsx) and in tests/unit.
 * TOKENS mirrors styles/tokens.css; tests/unit/tokens.test.ts fails if the
 * two drift, so a colour can't change in one place only. */

export const TOKENS = {
  light: {
    bg: "#ffffff", "bg-subtle": "#f8f8fb", "bg-muted": "#f1f1f5", surface: "#ffffff",
    text: "#12131e", "text-2": "#5a5c6b", "text-3": "#686a7a",
    brand: "#2446e0", "brand-hover": "#1c38b8", "brand-subtle": "#edf0fe", "on-brand": "#ffffff",
    highlight: "#5b4fd6", band: "#262a60",
    danger: "#c8322b", "danger-bg": "#fdeeed", warning: "#a35a00", "warning-bg": "#fff4de",
    success: "#157a4a", "success-bg": "#e7f6ee", neutral: "#55576a", "neutral-bg": "#f0f0f4",
  },
  dark: {
    bg: "#12121d", "bg-subtle": "#161724", "bg-muted": "#1b1c28", surface: "#1b1c2a", "surface-raised": "#1f2030",
    text: "#e9e9ed", "text-2": "#b2b6ca", "text-3": "#9397ab",
    brand: "#2446e0", "on-brand": "#ffffff", highlight: "#b5abfc", band: "#262a60", "outline-accent-bg": "#222134",
    danger: "#f47b74", warning: "#f2c06b", success: "#6dc88f", neutral: "#b2b6ca",
  },
  sheet: {
    "sheet-chrome": "#1d6b3a", "sheet-chrome-text": "#ffffff", "sheet-header": "#e8f5ea", "sheet-header-text": "#1f3a26",
    "sheet-body": "#f6f7f5", "sheet-index": "#6b6f68", "sheet-text": "#23262b",
    "cell-ok": "#e9f6eb", "cell-ok-text": "#1b5e34", "cell-warn": "#ffecc1", "cell-warn-text": "#7a4a00",
    "cell-error": "#fbd5d2", "cell-error-text": "#b0241b",
  },
} as const;

type Theme = keyof typeof TOKENS;

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

/** A translucent fill as it renders over its base (the dark status tints). */
export function composite(rgb: string, alpha: number, base: string): string {
  const [r, g, b] = hexToRgb(rgb);
  const [R, G, B] = hexToRgb(base);
  const mix = (f: number, k: number) => Math.round(f * alpha + k * (1 - alpha)).toString(16).padStart(2, "0");
  return `#${mix(r, R)}${mix(g, G)}${mix(b, B)}`;
}

const L = TOKENS.light;
const D = TOKENS.dark;
const S = TOKENS.sheet;
const t = (theme: Theme, name: string) => (TOKENS[theme] as Record<string, string>)[name];

// [label, foreground, background]
export const PAIRS: [string, string, string][] = [
  ...(["bg", "bg-subtle", "bg-muted", "surface"] as const).flatMap((bg) =>
    (["text", "text-2", "text-3"] as const).map((fg): [string, string, string] => [`light ${fg} on ${bg}`, L[fg], L[bg]])),
  ["light brand on bg", L.brand, L.bg],
  ["light brand on bg-subtle", L.brand, L["bg-subtle"]],
  ["light brand on brand-subtle", L.brand, L["brand-subtle"]],
  ["light on-brand on brand", L["on-brand"], L.brand],
  ["light on-brand on brand-hover", L["on-brand"], L["brand-hover"]],
  ["light highlight on bg", L.highlight, L.bg],
  ["light highlight on bg-subtle", L.highlight, L["bg-subtle"]],
  ["light on-brand on band", L["on-brand"], L.band],
  ...(["danger", "warning", "success", "neutral"] as const).flatMap((s): [string, string, string][] => [
    [`light ${s} on bg`, L[s], L.bg],
    [`light ${s} on ${s}-bg`, L[s], t("light", `${s}-bg`)],
  ]),
  ["light on-brand on danger", L["on-brand"], L.danger],
  ...(["bg", "bg-subtle", "bg-muted", "surface", "surface-raised"] as const).flatMap((bg) =>
    (["text", "text-2", "text-3"] as const).map((fg): [string, string, string] => [`dark ${fg} on ${bg}`, D[fg], D[bg]])),
  ["dark text on outline-accent-bg", D.text, D["outline-accent-bg"]],
  ["dark highlight on bg", D.highlight, D.bg],
  ["dark highlight on surface", D.highlight, D.surface],
  ["dark highlight on band", D.highlight, D.band],
  ["dark text on band", D.text, D.band],
  ["dark text-2 on band", D["text-2"], D.band],
  ["dark on-brand on brand", D["on-brand"], D.brand],
  ...(["danger", "warning", "success", "neutral"] as const).flatMap((s): [string, string, string][] => [
    [`dark ${s} on bg`, D[s], D.bg],
    [`dark ${s} on surface`, D[s], D.surface],
    [`dark ${s} on its tint`, D[s], composite(D[s], 0.12, D.bg)],
  ]),
  ["sheet text on body", S["sheet-text"], S["sheet-body"]],
  ["sheet index on body", S["sheet-index"], S["sheet-body"]],
  ["sheet header text on header", S["sheet-header-text"], S["sheet-header"]],
  ["sheet title on chrome", S["sheet-chrome-text"], S["sheet-chrome"]],
  ["cell ok text on ok", S["cell-ok-text"], S["cell-ok"]],
  ["cell warn text on warn", S["cell-warn-text"], S["cell-warn"]],
  ["cell error text on error", S["cell-error-text"], S["cell-error"]],
];

export function contrastFailures(min = 4.5): string[] {
  return PAIRS.filter(([, fg, bg]) => contrastRatio(fg, bg) < min).map(
    ([name, fg, bg]) => `${name}: ${contrastRatio(fg, bg).toFixed(2)}:1 (needs >= ${min}:1)`,
  );
}

export function validateDesignSystemContrast(): void {
  const failures = contrastFailures();
  if (failures.length > 0) {
    throw new Error(`Design system contrast validation failed:\n${failures.join("\n")}`);
  }
}

/** Status colours must stay distinct so severity is never carried by a colour another status also uses. */
export function validateDistinctFamilies(): void {
  for (const theme of [L, D]) {
    const families = [theme.success, theme.warning, theme.danger, theme.brand, theme.neutral];
    if (new Set(families).size !== families.length) {
      throw new Error("Two status families share a colour value");
    }
  }
}
