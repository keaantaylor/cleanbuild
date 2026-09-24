import Link from "next/link";

export default function NotFound() {
  return (
    <div style={{ maxWidth: 560, margin: "14vh auto", padding: 24 }}>
      <p style={{ fontSize: 12, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--color-primary)" }}>Not found</p>
      <h1 style={{ fontFamily: "var(--font-display)", fontSize: 28, margin: "6px 0 12px" }}>This page doesn&rsquo;t exist</h1>
      <p style={{ color: "var(--color-text-secondary)" }}>The link may be out of date, or the report may have been deleted or expired.</p>
      <p><Link href="/overview">Go to the overview</Link></p>
    </div>
  );
}
