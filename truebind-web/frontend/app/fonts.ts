import localFont from "next/font/local";

// Self-hosted (SIL OFL 1.1, see app/fonts/OFL.txt): no network fetch at build time.
// Inter matches the landing mockup; IBM Plex Mono carries codes, cell values and hashes.
export const inter = localFont({
  src: "./fonts/Inter-Variable-latin.woff2",
  weight: "100 900",
  variable: "--font-inter",
  display: "swap",
});

export const plexMono = localFont({
  src: [
    { path: "./fonts/IBMPlexMono-Regular-latin.woff2", weight: "400" },
    { path: "./fonts/IBMPlexMono-Medium-latin.woff2", weight: "500" },
  ],
  variable: "--font-plex-mono",
  display: "swap",
});
