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

// Nocturne, dark theme (the default). Grounds: bg #161826, bg2 #1b1d2b,
// surface #1f2130, surface2 #262838, chrome (sidebar / site) #12131e.
const DARK_PAIRS: [string, string, string][] = [
  ["text on bg", "#E9E9ED", "#161826"],
  ["text on surface", "#E9E9ED", "#1F2130"],
  ["muted on bg", "#9397AB", "#161826"],
  ["muted on surface", "#9397AB", "#1F2130"],
  ["muted on surface2", "#9397AB", "#262838"],
  ["faint on bg", "#8B8FA2", "#161826"],
  ["faint on bg2", "#8B8FA2", "#1B1D2B"],
  ["faint on surface", "#8B8FA2", "#1F2130"],
  ["faint on surface2", "#8B8FA2", "#262838"],
  ["accentText on bg", "#D2CEFD", "#161826"],
  ["accentText on surface", "#D2CEFD", "#1F2130"],
  ["kicker on chrome", "#B5ABFC", "#12131E"],
  ["chromeText on chrome", "#CFD3E5", "#12131E"],
  ["chromeMuted on chrome", "#B2B6CA", "#12131E"],
  ["chromeFaint on chrome", "#808493", "#12131E"],
  // Status colours are oklch() in CSS; these are their exact sRGB values.
  ["ok on surface", "#6DC88F", "#1F2130"],
  ["warn on surface", "#EEB563", "#1F2130"],
  ["err on surface", "#F47B74", "#1F2130"],
  ["med on surface", "#8CB1E0", "#1F2130"],
  ["on-accent on solid accent", "#161826", "#9184D9"],
  ["toast text on glass", "#E9E9ED", "#232532"],
];

// Nocturne, light theme. Grounds: bg #f4f5fa, bg2 #eceef6, surface #fcfcfe,
// surface2 #f1f2f8, chrome #ecedf5; the Health Check document is #fbfbfd.
const LIGHT_PAIRS: [string, string, string][] = [
  ["text on bg", "#1C1E2A", "#F4F5FA"],
  ["text on surface", "#1C1E2A", "#FCFCFE"],
  ["muted on bg", "#595D6C", "#F4F5FA"],
  ["muted on bg2", "#595D6C", "#ECEEF6"],
  ["faint on bg", "#676B7E", "#F4F5FA"],
  ["faint on bg2", "#676B7E", "#ECEEF6"],
  ["faint on surface", "#676B7E", "#FCFCFE"],
  ["faint on surface2", "#676B7E", "#F1F2F8"],
  ["accentText on bg", "#5D5294", "#F4F5FA"],
  ["accentText on surface", "#5D5294", "#FCFCFE"],
  ["chromeFaint on chrome", "#676B7E", "#ECEDF5"],
  ["chromeMuted on chrome", "#595D6C", "#ECEDF5"],
  ["report body on paper", "#3F424D", "#FBFBFD"],
  ["report label on paper", "#595D6C", "#FBFBFD"],
  ["report caption on paper", "#676B7E", "#FBFBFD"],
  ["ok on bg", "#1E7546", "#F4F5FA"],
  ["warn on bg2", "#9D5D03", "#ECEEF6"],
  ["err on bg", "#BD3838", "#F4F5FA"],
  ["med on bg", "#39659B", "#F4F5FA"],
  ["count badge text on badge red (both themes)", "#FFFFFF", "#C8473A"],
  ["on-accent on solid accent", "#FFFFFF", "#6E61B3"],
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

/** Status colours must stay distinct from one another so severity is never
 * carried by a colour another status also uses. */
export function validateDistinctFamilies(): void {
  const families = ["#6DC88F", "#EEB563", "#F47B74", "#8CB1E0", "#9397AB", "#1E7546", "#9D5D03", "#BD3838", "#39659B"];
  if (new Set(families).size !== families.length) {
    throw new Error("Two status families share a colour value");
  }
}
