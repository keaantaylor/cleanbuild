import { Inter, Space_Grotesk } from "next/font/google";
import "@/styles/marketing.css";
import { MarketingNav } from "@/components/marketing/MarketingNav";
import { MarketingFooter } from "@/components/marketing/MarketingFooter";

const display = Space_Grotesk({ subsets: ["latin"], weight: ["500", "600", "700"], variable: "--font-display" });
const body = Inter({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-marketing-body" });

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={`mkt-shell ${display.variable} ${body.variable}`} style={{ fontFamily: "var(--font-marketing-body)" }}>
      <MarketingNav />
      <main>{children}</main>
      <MarketingFooter />
    </div>
  );
}
