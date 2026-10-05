import { MarketingShell } from "@/components/layout/MarketingShell";

// Dark marketing chrome (nav + footer) around every public page.
export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return <MarketingShell>{children}</MarketingShell>;
}
