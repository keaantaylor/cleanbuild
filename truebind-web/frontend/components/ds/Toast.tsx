"use client";

import { CheckCircle, Info, Warning, WarningCircle } from "@phosphor-icons/react";
import { useUi } from "@/lib/ui";
import s from "./Toast.module.css";

const ICON = { ok: CheckCircle, info: Info, warn: Warning, err: WarningCircle };

/** Toasts from lib/ui's toast(); announced politely to screen readers. */
export function Toaster() {
  const { toasts } = useUi();
  return (
    <div className={`${s.region} no-print`} aria-live="polite" aria-atomic="false">
      {toasts.map((t) => {
        const Icon = ICON[t.tone];
        return (
          <div key={t.id} className={`${s.toast} ${s[t.tone]}`} role={t.tone === "err" ? "alert" : "status"}>
            <Icon size={16} weight="bold" aria-hidden="true" />
            <span>{t.text}</span>
          </div>
        );
      })}
    </div>
  );
}
