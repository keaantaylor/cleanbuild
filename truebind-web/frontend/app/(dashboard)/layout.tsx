import { Suspense } from "react";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { AuthGate } from "@/components/auth/AuthGate";

export default function DashboardGroupLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <DashboardLayout>
        <Suspense fallback={<p>Loading…</p>}>{children}</Suspense>
      </DashboardLayout>
    </AuthGate>
  );
}
