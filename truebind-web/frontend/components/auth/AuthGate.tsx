"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { Me } from "@/lib/types";
import { ErrorState, Mark, Skeleton } from "@/components/nocturne/ui";

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

  // Senders (coverholder / TPA users) have their own portal and no access to the provider's workspace.
  const senderElsewhere = me?.role === "SENDER" && !pathname.startsWith("/sender") && !pathname.startsWith("/settings");
  useEffect(() => {
    if (senderElsewhere) router.replace("/sender");
  }, [senderElsewhere, router]);

  if (error) {
    return (
      <div className="mx-auto flex max-w-[560px] flex-col gap-4 px-6 pt-[12vh]">
        <span className="flex items-center gap-2 text-[15px] font-semibold"><Mark size={24} />TrueBind</span>
        <ErrorState title="TrueBind can’t reach its server" onRetry={check}
          message={`The web app is running but the TrueBind API did not respond (${error}). If you are running locally, start the backend (./dev.ps1 or ./dev.sh starts everything), then try again.`} />
      </div>
    );
  }
  if (!me) return <SessionSkeleton message="Checking your session…" />;
  if (senderElsewhere) return <SessionSkeleton message="Opening the sender portal…" />;
  return <MeContext.Provider value={me}>{children}</MeContext.Provider>;
}

/** Shaped like the app shell so the page doesn't jump when the session resolves. */
function SessionSkeleton({ message }: { message: string }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] min-h-screen lg:grid-cols-[232px_minmax(0,1fr)]" role="status" aria-live="polite" style={{ background: "var(--bg)" }}>
      <div className="hidden flex-col gap-4 px-4 py-5 lg:flex" style={{ background: "var(--chrome)" }}>
        <span className="flex items-center gap-2 text-[15px] font-semibold" style={{ color: "var(--chromeStrong)" }}><Mark size={26} />TrueBind</span>
        {Array.from({ length: 9 }, (_, i) => <Skeleton key={i} h={14} w={`${70 - (i % 3) * 12}%`} />)}
      </div>
      <div className="flex flex-col gap-4 px-9 pt-8">
        <span className="sr-only">{message}</span>
        <Skeleton h={12} w={180} />
        <Skeleton h={30} w={260} />
        <Skeleton h={120} />
        <Skeleton h={260} />
      </div>
    </div>
  );
}
