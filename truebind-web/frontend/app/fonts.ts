import localFont from "next/font/local";

// Self-hosted (SIL OFL 1.1, see app/fonts/OFL.txt). next/font/google made
// the dev server and `next build` fetch fonts from Google at compile time;
// when that fetch or Turbopack's internal font module failed to resolve,
// the whole layout errored ("Can't resolve
// '@vercel/turbopack-next/internal/font/google/font'"). Local files have no
// network dependency and are served from our own origin.
export const displayFont = localFont({
  src: "./fonts/SpaceGrotesk-Variable-latin.woff2",
  weight: "300 700",
  variable: "--font-display-face",
  display: "swap",
});

export const bodyFont = localFont({
  src: "./fonts/Inter-Variable-latin.woff2",
  weight: "100 900",
  variable: "--font-body-face",
  display: "swap",
});
