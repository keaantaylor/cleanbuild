import "@/styles/marketing.css";
import { MarketingNav } from "@/components/marketing/MarketingNav";
import { MarketingFooter } from "@/components/marketing/MarketingFooter";

// Fonts are self-hosted and applied once in the root layout (app/fonts.ts).
export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mkt-shell" style={{ fontFamily: "var(--font-sans)" }}>
      <MarketingNav />
      <main>{children}</main>
      <MarketingFooter />
    </div>
  );
}
