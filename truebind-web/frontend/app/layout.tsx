import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "@/styles/globals.css";
import { validateDesignSystemContrast, validateDistinctFamilies } from "@/lib/colorContrast";
import { DEVICE_SCRIPT, THEME_SCRIPT } from "@/lib/boot-scripts";
import { Providers } from "@/components/nocturne/providers";

validateDesignSystemContrast();
validateDistinctFamilies();

// Self-hosted (SIL OFL 1.1, see app/fonts/OFL.txt): no network fetch at build time.
const inter = localFont({
  src: "./fonts/Inter-Variable-latin.woff2",
  weight: "100 900",
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "TrueBind · Clean claims bordereaux",
  description:
    "TrueBind maps, validates and reconciles claims bordereaux before they reach carriers, with clear evidence of what was checked and what was not.",
  icons: { icon: "/assets/mark.png" },
};

// viewport-fit=cover lets the layout run under the notch / Dynamic Island and
// home indicator; padding uses env(safe-area-inset-*) to keep content clear.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#161826" },
    { media: "(prefers-color-scheme: light)", color: "#f4f5fa" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-IE" data-theme="dark" className={inter.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT + DEVICE_SCRIPT }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
