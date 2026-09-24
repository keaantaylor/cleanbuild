"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { SystemStatus } from "@/lib/types";

interface ShellState {
  system: SystemStatus | null;
  unreadAlerts: number;
  workItems: number;
  refresh: () => void;
}

const Ctx = createContext<ShellState>({ system: null, unreadAlerts: 0, workItems: 0, refresh: () => {} });
export const useShell = () => useContext(Ctx);

/** One poller for the chrome (processing-service status, unread alerts, work
 * queue size) so individual pages never duplicate these requests. Pauses
 * while the tab is hidden. */
export function ShellProvider({ children }: { children: React.ReactNode }) {
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [unreadAlerts, setUnread] = useState(0);
  const [workItems, setWork] = useState(0);
  const inflight = useRef(false);

  const refresh = useCallback(async () => {
    if (inflight.current || (typeof document !== "undefined" && document.hidden)) return;
    inflight.current = true;
    try {
      const [sys, alerts, work] = await Promise.all([
        api.systemStatus(), api.countUnreadAlerts(), api.workQueue(),
      ]);
      setSystem(sys);
      setUnread(alerts);
      setWork(work.total);
    } catch {
      // chrome must never break the page; the next tick retries
    } finally {
      inflight.current = false;
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(refresh, 0);
    const t = setInterval(refresh, 15_000);
    const onVis = () => { if (!document.hidden) refresh(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { clearTimeout(first); clearInterval(t); document.removeEventListener("visibilitychange", onVis); };
  }, [refresh]);

  return <Ctx.Provider value={{ system, unreadAlerts, workItems, refresh }}>{children}</Ctx.Provider>;
}
