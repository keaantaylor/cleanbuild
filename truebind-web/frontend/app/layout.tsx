import type { Metadata } from "next";
import "@/styles/globals.css";
import { validateDesignSystemContrast, validateDistinctFamilies } from "@/lib/colorContrast";

validateDesignSystemContrast();
validateDistinctFamilies();

export const metadata: Metadata = {
  title: "Truebind",
  description: "Claims bordereaux aggregation, validation and leakage detection",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
