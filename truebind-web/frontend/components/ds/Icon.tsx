/** Minimal stroke icon set (24px grid, currentColor). Decorative by default;
 * pass `label` when an icon carries meaning on its own. */
const PATHS: Record<string, string> = {
  overview: "M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z",
  inbox: "M3 13l3-8h12l3 8v6H3zM3 13h5l1 3h6l1-3h5",
  upload: "M12 16V4M7 9l5-5 5 5M4 16v4h16v-4",
  reports: "M5 3h10l4 4v14H5zM15 3v4h4M8 12h8M8 16h8M8 8h4",
  exceptions: "M12 3l10 18H2zM12 10v5M12 18h.01",
  duplicates: "M8 8h12v12H8zM4 16V4h12",
  exports: "M4 12l16-8-6 16-2-7z",
  automations: "M13 2L4 14h7l-1 8 9-12h-7z",
  audit: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM9 12l2 2 4-4",
  todo: "M4 5h16v16H4zM8 11l2 2 5-5",
  bell: "M6 16V11a6 6 0 0112 0v5l2 2H4zM10 21h4",
  activity: "M3 12h4l3 8 4-16 3 8h4",
  file: "M6 3h8l4 4v14H6zM14 3v4h4",
  chevronRight: "M9 6l6 6-6 6",
  chevronDown: "M6 9l6 6 6-6",
  refresh: "M4 12a8 8 0 0114-5l2 2M20 12a8 8 0 01-14 5l-2-2M20 4v5h-5M4 20v-5h5",
  download: "M12 4v12M7 11l5 5 5-5M4 20h16",
  mail: "M3 5h18v14H3zM3 6l9 7 9-7",
  search: "M11 4a7 7 0 100 14 7 7 0 000-14zM16 16l5 5",
  x: "M6 6l12 12M18 6L6 18",
  clock: "M12 3a9 9 0 100 18 9 9 0 000-18zM12 7v5l3 2",
  check: "M5 12l5 5 9-10",
  alertCircle: "M12 3a9 9 0 100 18 9 9 0 000-18zM12 8v5M12 16h.01",
  info: "M12 3a9 9 0 100 18 9 9 0 000-18zM12 11v6M12 7h.01",
  sparkles: "M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z",
  server: "M4 4h16v6H4zM4 14h16v6H4zM8 7h.01M8 17h.01",
  layers: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5",
  logout: "M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10",
  arrowRight: "M5 12h14M13 6l6 6-6 6",
  link: "M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1",
  user: "M12 4a4 4 0 100 8 4 4 0 000-8zM4 20a8 8 0 0116 0",
  command: "M9 6a3 3 0 10-3 3h12a3 3 0 10-3-3v12a3 3 0 103-3H6a3 3 0 103 3z",
  filter: "M4 5h16l-6 8v6l-4 2v-8z",
  calendar: "M4 6h16v14H4zM4 10h16M8 3v5M16 3v5",
  database: "M12 3c4.4 0 8 1.3 8 3s-3.6 3-8 3-8-1.3-8-3 3.6-3 8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  lineage: "M6 3v6a3 3 0 003 3h6a3 3 0 013 3v6M6 3a2 2 0 100 .01M18 21a2 2 0 100-.01M6 9v12",
  send: "M4 12l16-8-6 16-2-7zM12 13l8-9",
  table: "M4 5h16v14H4zM4 10h16M4 15h16M10 5v14",
  pound: "M16 6.5A4 4 0 009 8v4H7M7 12h7M9 12v2a4 4 0 01-2 3.5V19h11",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 100 6 3 3 0 000-6z",
  arrowUpRight: "M7 17L17 7M9 7h8v8",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  merge: "M6 3v6a6 6 0 006 6h6M15 12l3 3-3 3M6 21v-6",
  play: "M7 4l13 8-13 8z",
};

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 16, label, className, strokeWidth = 1.8 }: {
  name: IconName; size?: number; label?: string; className?: string; strokeWidth?: number;
}) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth}
         strokeLinecap="round" strokeLinejoin="round" className={className}
         role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true} focusable="false">
      <path d={PATHS[name]} />
    </svg>
  );
}
