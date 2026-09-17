import styles from "./CoverageBanner.module.css";

export function CoverageBanner({
  rowsAssessed, rowsTotal, sheetsProcessed, sheetsTotal,
}: { rowsAssessed: number; rowsTotal: number; sheetsProcessed: number; sheetsTotal: number }) {
  const fullyCovered = rowsAssessed === rowsTotal && sheetsProcessed === sheetsTotal;
  return (
    <div className={`${styles.banner} ${fullyCovered ? styles.full : styles.partial}`}>
      <span aria-hidden="true">{fullyCovered ? "✓" : "⚠"}</span>
      Assessed {rowsAssessed} of {rowsTotal} rows across {sheetsProcessed} of {sheetsTotal} sheets.
      {!fullyCovered && " Some rows or sheets were not assessed — the score below may not be fully reliable."}
    </div>
  );
}
