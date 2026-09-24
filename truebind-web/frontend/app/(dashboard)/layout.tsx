import { Suspense } from "react";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { AuthGate } from "@/components/auth/AuthGate";
import { PageSkeleton } from "@/components/layout/ShellSkeleton";

export default function DashboardGroupLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <DashboardLayout>
        <Suspense fallback={<PageSkeleton />}>{children}</Suspense>
      </DashboardLayout>
    </AuthGate>
  );
}
