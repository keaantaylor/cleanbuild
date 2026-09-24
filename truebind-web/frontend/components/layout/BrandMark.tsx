/** TrueBind mark: three loose strands (incoming data) pulled through a
 * binding bar into three aligned rows (structured output). Pure SVG. */
export function BrandMark({ size = 30, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="8" fill="#2446E0" />
      <path d="M5 9c3 0 4 3 8 3M5 16h8M5 23c3 0 4-3 8-3" stroke="#B9C6FF" strokeWidth="1.8" fill="none" strokeLinecap="round" />
      <rect x="13" y="7" width="3.2" height="18" rx="1.6" fill="#6FE3C1" />
      <path d="M19 11h8M19 16h8M19 21h8" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
