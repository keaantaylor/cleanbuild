import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { DesignSystemGallery } from "./gallery";

export const metadata: Metadata = { title: "Design system", robots: { index: false } };

// Development reference only: 404 in production unless explicitly enabled for a review build.
export default async function DesignSystemPage({ searchParams }: { searchParams: Promise<{ theme?: string }> }) {
  if (process.env.NODE_ENV === "production" && process.env.NEXT_PUBLIC_DESIGN_SYSTEM !== "1") notFound();
  const { theme } = await searchParams;
  return <DesignSystemGallery initialTheme={theme === "dark" ? "dark" : "light"} />;
}
