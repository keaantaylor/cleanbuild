"use client";

import { UiProvider } from "@/lib/ui";
import { Toaster } from "./ui";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <UiProvider>
      {children}
      <Toaster />
    </UiProvider>
  );
}
