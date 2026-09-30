"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

/* UI-only state: theme and toasts. Everything else comes from the API. */

export type Theme = "dark" | "light";
export type Toast = { id: number; text: string; tone: "ok" | "info" | "warn" | "err" };

type Ui = {
  theme: Theme;
  toggleTheme: () => void;
  toast: (text: string, tone?: Toast["tone"]) => void;
  toasts: Toast[];
};

const Ctx = createContext<Ui | null>(null);

export function UiProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>("dark");
  const [toasts, setToasts] = useState<Toast[]>([]);
  const tid = useRef(0);

  useEffect(() => {
    // The theme script in the root layout already set <html data-theme>; mirror it.
    const t = document.documentElement.dataset.theme;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (t === "light" || t === "dark") setTheme(t);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((p) => {
      const next = p === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try {
        localStorage.setItem("tb-theme", next);
      } catch {
        // storage unavailable: the choice still applies to this page
      }
      return next;
    });
  }, []);

  const toast = useCallback((text: string, tone: Toast["tone"] = "ok") => {
    const id = ++tid.current;
    setToasts((t) => [...t.slice(-2), { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3600);
  }, []);

  return <Ctx.Provider value={{ theme, toggleTheme, toast, toasts }}>{children}</Ctx.Provider>;
}

export function useUi() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useUi must be used inside <UiProvider>");
  return c;
}
