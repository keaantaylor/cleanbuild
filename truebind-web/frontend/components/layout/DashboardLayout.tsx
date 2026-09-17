import { Sidebar } from "./Sidebar";
import { TopNav } from "./TopNav";
import styles from "./DashboardLayout.module.css";

export function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={styles.shell}>
      <Sidebar />
      <div className={styles.column}>
        <TopNav />
        <main className={styles.main}>{children}</main>
      </div>
    </div>
  );
}
