/** Decorative engine glyph: loose strands (incoming rows) pulled through the
 * binding bar into aligned rows. It animates only while a job is actually
 * running and never encodes progress. Static under reduced motion. */
import styles from "./intake.module.css";

export function EngineVisual({ active, size = 88 }: { active: boolean; size?: number }) {
  return (
    <svg className={`${styles.engine} ${active ? styles.engineOn : ""}`} width={size} height={size} viewBox="0 0 88 88"
         aria-hidden="true" focusable="false">
      <rect x="1" y="1" width="86" height="86" rx="20" className={styles.engineBg} />
      <g className={styles.strands}>
        <path d="M10 26c10 0 14 10 26 12" />
        <path d="M10 44c9 0 15-4 26-2" />
        <path d="M10 62c10 0 14-12 26-16" />
      </g>
      <rect x="37" y="18" width="7" height="52" rx="3.5" className={styles.bind} />
      <g className={styles.rows}>
        <path d="M50 32h28" /><path d="M50 44h28" /><path d="M50 56h28" />
      </g>
      <circle className={styles.pulseDot} cx="40.5" cy="44" r="2.2" />
    </svg>
  );
}
