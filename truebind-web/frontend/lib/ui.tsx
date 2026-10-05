"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

/* UI-only state: toasts. Everything else comes from the API. */

export type Toast = { id: number; text: string; tone: "ok" | "info" | "warn" | "err" };

type Ui = {
  toast: (text: string, tone?: Toast["tone"]) => void;
  toasts: Toast[];
};

const Ctx = createContext<Ui | null>(null);

export function UiProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const tid = useRef(0);

  const toast = useCallback((text: string, tone: Toast["tone"] = "ok") => {
    const id = ++tid.current;
    setToasts((t) => [...t.slice(-2), { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3600);
  }, []);

  return <Ctx.Provider value={{ toast, toasts }}>{children}</Ctx.Provider>;
}

export function useUi() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useUi must be used inside <UiProvider>");
  return c;
}
