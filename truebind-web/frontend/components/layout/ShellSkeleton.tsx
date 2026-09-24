import { Skeleton } from "@/components/ds";
import styles from "./ShellSkeleton.module.css";

/** Content-area skeleton: header, a row of tiles and two panels. Shown for
 * route transitions (app/(dashboard)/loading.tsx) and while data loads. */
export function PageSkeleton({ label = "Loading" }: { label?: string }) {
  return (
    <div className={styles.page} aria-busy="true" aria-label={label}>
      <Skeleton width={120} height={12} />
      <Skeleton width={320} height={30} />
      <div className={styles.tiles}>
        {[0, 1, 2, 3].map((i) => <div key={i} className={styles.tile}><Skeleton width="50%" height={12} /><Skeleton width="35%" height={28} /></div>)}
      </div>
      <div className={styles.panels}>
        <div className={styles.panel}><Skeleton width="30%" height={14} /><Skeleton height={12} /><Skeleton height={12} width="85%" /><Skeleton height={12} width="70%" /></div>
        <div className={styles.panel}><Skeleton width="40%" height={14} /><Skeleton height={12} /><Skeleton height={12} width="60%" /></div>
      </div>
    </div>
  );
}

/** Whole-app skeleton (rail + top bar + page) shown while the session is
 * being checked, so the first paint already looks like the product. */
export function ShellSkeleton({ message }: { message?: string }) {
  return (
    <div className={styles.shell}>
      <div className={styles.rail} aria-hidden="true">
        <div className={styles.brand}><span className={styles.mark}>TB</span>TrueBind</div>
        {Array.from({ length: 9 }, (_, i) => <span key={i} className={styles.railItem} />)}
      </div>
      <div className={styles.column}>
        <div className={styles.topbar}>{message && <span className={styles.message}>{message}</span>}</div>
        <div className={styles.main}><PageSkeleton label={message ?? "Loading"} /></div>
      </div>
    </div>
  );
}
