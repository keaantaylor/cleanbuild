import { AuthGate } from "@/components/auth/AuthGate";
import { SenderShell } from "@/components/nocturne/sender-shell";

export default function SenderLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <SenderShell>{children}</SenderShell>
    </AuthGate>
  );
}
