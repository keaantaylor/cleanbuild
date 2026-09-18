import type { Metadata } from "next";
import { Hero } from "@/components/marketing/Hero";
import { ProblemSection } from "@/components/marketing/ProblemSection";
import { HowItWorksStepper } from "@/components/marketing/HowItWorksStepper";
import { AiShowcase } from "@/components/marketing/AiShowcase";
import { SavingsCalculator } from "@/components/marketing/SavingsCalculator";
import { TrustSection } from "@/components/marketing/TrustSection";
import { ClosingCta } from "@/components/marketing/ClosingCta";

export const metadata: Metadata = {
  title: "Truebind — Audited bordereau processing",
  description: "Truebind ingests multi-sheet, multi-currency bordereaux, maps and validates every field, and returns an audited exception report.",
};

export default function MarketingHomePage() {
  return (
    <>
      <Hero />
      <ProblemSection />
      <HowItWorksStepper />
      <AiShowcase />
      <SavingsCalculator />
      <TrustSection />
      <ClosingCta />
    </>
  );
}
