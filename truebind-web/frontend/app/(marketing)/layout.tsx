// Fonts are self-hosted and applied once in the root layout (app/fonts.ts).
// The landing page carries its own navigation and footer.
export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
