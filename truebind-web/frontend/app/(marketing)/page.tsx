import type { Metadata } from "next";
import { Landing } from "@/components/landing/Landing";

export const metadata: Metadata = {
  title: "TrueBind — insurance data, finally in motion",
  description: "TrueBind turns the bordereaux your partners send into validated, reconciled, explainable data: mapping, validation, duplicate intelligence and a verifiable audit trail.",
};

export default function MarketingHomePage() {
  return <Landing />;
}
