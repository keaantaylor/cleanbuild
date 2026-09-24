"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { Me } from "@/lib/types";
import { ShellSkeleton } from "@/components/layout/ShellSkeleton";
import { ErrorState } from "@/components/ds";

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);

/** Client-side gate. The API enforces auth on every request; this decides
 * what to render: a shaped skeleton while checking, the app when signed in,
 * a redirect to /login only on 401, and an explained, retryable error when
 * the API itself cannot be reached (never a blank screen, never a loop). */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);

  const check = useCallback(() => {
    setError(null);
    api.me()
      .then(setMe)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) {
          router.replace(`/login?next=${encodeURIComponent(pathname)}`);
        } else {
          setError(e instanceof ApiError ? e.message : "The TrueBind API could not be reached.");
        }
      });
  }, [router, pathname]);

  useEffect(() => {
    if (me) return;
    const t = setTimeout(check, 0);
    return () => clearTimeout(t);
  }, [check, me]);

  if (error) {
    return (
      <div style={{ maxWidth: 560, margin: "12vh auto", padding: 24 }}>
        <ErrorState title="TrueBind can't reach its server" onRetry={check}
          message="The web app is running but the TrueBind API did not respond. If you are running locally, start the backend (./dev.ps1 or ./dev.sh starts everything), then try again."
          details={error} />
      </div>
    );
  }
  if (!me) return <ShellSkeleton message="Checking your session…" />;
  return <MeContext.Provider value={me}>{children}</MeContext.Provider>;
}
