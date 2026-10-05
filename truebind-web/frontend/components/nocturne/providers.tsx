"use client";

import { UiProvider } from "@/lib/ui";
import { Toaster } from "@/components/ds";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <UiProvider>
      {children}
      <Toaster />
    </UiProvider>
  );
}
