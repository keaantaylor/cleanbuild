import { Sidebar } from "./Sidebar";
import { TopNav } from "./TopNav";
import { ShellProvider } from "./ShellContext";
import { CommandPalette } from "./CommandPalette";
import { ToastProvider } from "@/components/ds/overlays";
import styles from "./DashboardLayout.module.css";

export function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <ShellProvider>
      <ToastProvider>
        <a href="#main" className={styles.skip}>Skip to content</a>
        <div className={styles.shell}>
          <Sidebar />
          <div className={styles.column}>
            <TopNav />
            <main id="main" className={styles.main} tabIndex={-1}>{children}</main>
          </div>
        </div>
        <CommandPalette />
      </ToastProvider>
    </ShellProvider>
  );
}
