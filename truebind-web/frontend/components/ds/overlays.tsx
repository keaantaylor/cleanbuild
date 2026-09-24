"use client";

/* Overlays: Drawer, Modal and Toasts. Drawer and Modal use the native
 * <dialog> element (showModal), so focus is trapped, Escape closes, the page
 * behind is inert and focus returns to the opener -- without a library. */

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import s from "./overlays.module.css";

function useDialog(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    const handle = (e: Event) => { e.preventDefault(); onClose(); };
    d.addEventListener("cancel", handle);
    return () => d.removeEventListener("cancel", handle);
  }, [onClose]);
  const onBackdrop = (e: React.MouseEvent<HTMLDialogElement>) => { if (e.target === e.currentTarget) onClose(); };
  return { ref, onBackdrop };
}

export function Drawer({ open, onClose, title, eyebrow, children, footer, width = 560 }: {
  open: boolean; onClose: () => void; title: ReactNode; eyebrow?: ReactNode; children: ReactNode;
  footer?: ReactNode; width?: number;
}) {
  const { ref, onBackdrop } = useDialog(open, onClose);
  return (
    <dialog ref={ref} className={s.drawer} style={{ width: `min(${width}px, 100vw)` }} onClick={onBackdrop}
            aria-labelledby="drawer-title">
      {open && (
        <div className={s.drawerInner}>
          <header className={s.head}>
            <div style={{ minWidth: 0 }}>
              {eyebrow && <p className={s.eyebrow}>{eyebrow}</p>}
              <h2 id="drawer-title" className={s.title}>{title}</h2>
            </div>
            <button type="button" className={s.close} onClick={onClose} aria-label="Close panel"><Icon name="x" size={18} /></button>
          </header>
          <div className={s.body}>{children}</div>
          {footer && <footer className={s.foot}>{footer}</footer>}
        </div>
      )}
    </dialog>
  );
}

export function Modal({ open, onClose, title, children, footer }: {
  open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode;
}) {
  const { ref, onBackdrop } = useDialog(open, onClose);
  return (
    <dialog ref={ref} className={s.modal} onClick={onBackdrop} aria-labelledby="modal-title">
      {open && (
        <div className={s.modalInner}>
          <header className={s.head}>
            <h2 id="modal-title" className={s.title}>{title}</h2>
            <button type="button" className={s.close} onClick={onClose} aria-label="Close dialog"><Icon name="x" size={18} /></button>
          </header>
          <div className={s.body}>{children}</div>
          {footer && <footer className={s.foot}>{footer}</footer>}
        </div>
      )}
    </dialog>
  );
}

/* ---------------------------------------------------------------- toasts */

type ToastTone = "good" | "bad" | "info" | "processing";
type Toast = { id: number; tone: ToastTone; title: string; body?: string; action?: { label: string; href: string } };
const ToastCtx = createContext<(t: Omit<Toast, "id">) => void>(() => {});

const TOAST_ICON: Record<ToastTone, IconName> = { good: "check", bad: "alertCircle", info: "info", processing: "activity" };

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);
  const dismiss = useCallback((id: number) => setToasts((ts) => ts.filter((t) => t.id !== id)), []);
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = ++seq.current;
    setToasts((ts) => [...ts.slice(-3), { ...t, id }]);
    window.setTimeout(() => dismiss(id), t.tone === "bad" ? 9000 : 5500);
  }, [dismiss]);
  const value = useMemo(() => push, [push]);
  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div className={s.toasts} role="region" aria-label="Notifications" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`${s.toast} ${s[`toast-${t.tone}`]}`} role={t.tone === "bad" ? "alert" : "status"}>
            <span className={s.toastIcon}><Icon name={TOAST_ICON[t.tone]} size={16} /></span>
            <div style={{ minWidth: 0, flex: 1 }}>
              <p className={s.toastTitle}>{t.title}</p>
              {t.body && <p className={s.toastBody}>{t.body}</p>}
              {t.action && <a className={s.toastAction} href={t.action.href}>{t.action.label} →</a>}
            </div>
            <button type="button" className={s.toastClose} onClick={() => dismiss(t.id)} aria-label="Dismiss notification">
              <Icon name="x" size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}
