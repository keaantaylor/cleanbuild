import type { Metadata } from "next";
import { Landing } from "@/components/site/landing";

export const metadata: Metadata = {
  title: "TrueBind · Clean claims bordereaux",
  description: "TrueBind maps, validates and reconciles claims bordereaux before they reach carriers, with clear evidence of what was checked and what was not.",
};

export default function MarketingHomePage() {
  return <Landing />;
}
