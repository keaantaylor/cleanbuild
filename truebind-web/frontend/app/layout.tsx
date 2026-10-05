import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "@/styles/globals.css";
import { validateDesignSystemContrast, validateDistinctFamilies } from "@/lib/colorContrast";
import { DEVICE_SCRIPT } from "@/lib/boot-scripts";
import { Providers } from "@/components/nocturne/providers";

validateDesignSystemContrast();
validateDistinctFamilies();

// Self-hosted (SIL OFL 1.1, see app/fonts/OFL.txt): no network fetch at build time.
const plex = localFont({
  src: "./fonts/IBMPlexSans-Variable-latin.woff2",
  weight: "400 700",
  variable: "--font-plex",
  display: "swap",
});
const plexMono = localFont({
  src: [
    { path: "./fonts/IBMPlexMono-Regular-latin.woff2", weight: "400" },
    { path: "./fonts/IBMPlexMono-Medium-latin.woff2", weight: "500" },
  ],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://truebind.ie"),
  title: { default: "TrueBind: workbook validation and reconciliation", template: "%s | TrueBind" },
  description:
    "TrueBind checks bordereaux and other large workbooks against versioned rules, points to the exact cell that needs attention, and keeps an audit trail of every correction.",
  icons: { icon: "/assets/mark.png" },
};

// viewport-fit=cover lets the layout run under the notch / Dynamic Island and
// home indicator; padding uses env(safe-area-inset-*) to keep content clear.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#ffffff",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-IE" data-theme="light" className={`${plex.variable} ${plexMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: DEVICE_SCRIPT }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
