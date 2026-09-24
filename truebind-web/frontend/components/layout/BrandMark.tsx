/** TrueBind mark, "the Binding Field": loose, uneven strokes (incoming
 * bordereau data) enter a binding ring and leave as three aligned rows in
 * Bind Green (structured, trusted data). `tone` picks the ink for light
 * (Paper) or dark (Carbon) surfaces. Pure inline SVG, decorative. */
export function BrandMark({ size = 30, tone = "dark", className }: {
  size?: number; tone?: "dark" | "light"; className?: string;
}) {
  const ink = tone === "dark" ? "#F6F8F5" : "#08111B";
  const loose = tone === "dark" ? "#8C99A5" : "#8A96A1";
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden="true" focusable="false">
      <g strokeLinecap="round" fill="none">
        <path d="M2.5 10.8 8 11.9M1.5 16h6.5M3.5 21.3 8.2 20.1" stroke={loose} strokeWidth="2" />
        <path d="M13 11.3h17M13 16h17M13 20.7h17" stroke="#00A980" strokeWidth="2.2" />
        <circle cx="15.5" cy="16" r="7.4" stroke={ink} strokeWidth="2.4" />
      </g>
    </svg>
  );
}

/** Mark plus wordmark, as used in navigation and the footer. */
export function BrandLockup({ tone = "dark", size = 28 }: { tone?: "dark" | "light"; size?: number }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 10, color: tone === "dark" ? "#F6F8F5" : "#08111B",
                   fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "1.1rem", letterSpacing: "-0.02em" }}>
      <BrandMark size={size} tone={tone} />
      TrueBind
    </span>
  );
}
