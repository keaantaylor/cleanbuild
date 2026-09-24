import localFont from "next/font/local";

// Geist Sans and Geist Mono (SIL OFL 1.1, see app/fonts/OFL.txt), self-hosted
// and subset to Latin plus the arrows/symbols the product uses. Local files
// keep builds free of any font-network dependency (next/font/google once
// broke Turbopack builds when its fetch failed).
export const geistSans = localFont({
  src: "./fonts/Geist-Variable-latin.woff2",
  weight: "100 900",
  variable: "--font-geist",
  display: "swap",
});

export const geistMono = localFont({
  src: "./fonts/GeistMono-Variable-latin.woff2",
  weight: "100 900",
  variable: "--font-geist-mono",
  display: "swap",
  preload: false, // only data tables and codes use it; never on the first paint path
});
