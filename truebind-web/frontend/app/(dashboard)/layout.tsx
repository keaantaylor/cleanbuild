import { AuthGate } from "@/components/auth/AuthGate";
import { DashboardShell } from "@/components/nocturne/dashboard-shell";

export default function DashboardGroupLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <DashboardShell>{children}</DashboardShell>
    </AuthGate>
  );
}
