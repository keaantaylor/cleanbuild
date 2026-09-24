"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);

/** Client-side gate: the API enforces auth on every request; this only
 * avoids rendering dashboard pages for a signed-out visitor. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    api.me()
      .then(setMe)
      .catch(() => router.replace(`/login?next=${encodeURIComponent(pathname)}`))
      .finally(() => setChecked(true));
  }, [router, pathname]);

  if (!checked || !me) return <p style={{ padding: 24 }}>Checking your session…</p>;
  return <MeContext.Provider value={me}>{children}</MeContext.Provider>;
}
