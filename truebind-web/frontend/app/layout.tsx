import type { Metadata, Viewport } from "next";
import { inter, plexMono } from "./fonts";
import "@/styles/globals.css";
import { validateDesignSystemContrast, validateDistinctFamilies } from "@/lib/colorContrast";
import { DEVICE_SCRIPT } from "@/lib/boot-scripts";
import { Providers } from "@/components/nocturne/providers";

validateDesignSystemContrast();
validateDistinctFamilies();

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
    <html lang="en-IE" data-theme="light" className={`${inter.variable} ${plexMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: DEVICE_SCRIPT }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
