"use client";

import { X } from "@phosphor-icons/react";
import Link from "next/link";
import { cloneElement, isValidElement, useCallback, useEffect, useId, useRef, useState } from "react";
import { Button } from "./Button";
import s from "./Overlay.module.css";

/** Drives a native modal <dialog> from an `open` prop. Focus moves into the
 * dialog, the page behind is inert, Esc and a backdrop click close it, and
 * focus returns to whatever opened it. */
function useModalDialog(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      opener.current = document.activeElement as HTMLElement | null;
      d.showModal();
      d.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    } else if (!open && d.open) {
      d.close();
    }
  }, [open]);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    const onCancel = (e: Event) => {
      e.preventDefault();
      onClose();
    };
    const onClosed = () => opener.current?.focus?.();
    d.addEventListener("cancel", onCancel);
    d.addEventListener("close", onClosed);
    return () => {
      d.removeEventListener("cancel", onCancel);
      d.removeEventListener("close", onClosed);
    };
  }, [onClose]);
  const onMouseDown = (e: React.MouseEvent<HTMLDialogElement>) => {
    if (e.target === e.currentTarget) onClose();
  };
  return { ref, onMouseDown };
}

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  width = 480,
}: {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  width?: number;
}) {
  const id = useId();
  const { ref, onMouseDown } = useModalDialog(open, onClose);
  return (
    <dialog
      ref={ref}
      className={`${s.dialog} ${s.modal}`}
      style={{ "--w": `${width}px` } as React.CSSProperties}
      aria-labelledby={`${id}-t`}
      aria-describedby={description ? `${id}-d` : undefined}
      onMouseDown={onMouseDown}
    >
      {open && (
        <div className={s.modalInner}>
          <div className={s.head}>
            <div>
              <h2 id={`${id}-t`} className={s.title}>{title}</h2>
              {description && <p id={`${id}-d`} className={s.desc}>{description}</p>}
            </div>
            <Button variant="ghost" size={28} iconOnly aria-label="Close" onClick={onClose}>
              <X size={16} />
            </Button>
          </div>
          {children && <div className={s.body}>{children}</div>}
          {footer && <div className={s.foot}>{footer}</div>}
        </div>
      )}
    </dialog>
  );
}

/** Right-hand panel, 560px (full width on phones). */
export function Drawer({
  open,
  onClose,
  title,
  meta,
  actions,
  children,
  label,
}: {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  meta?: React.ReactNode;
  actions?: React.ReactNode;
  children?: React.ReactNode;
  label?: string;
}) {
  const id = useId();
  const { ref, onMouseDown } = useModalDialog(open, onClose);
  return (
    <dialog ref={ref} className={`${s.dialog} ${s.drawer}`} aria-labelledby={label ? undefined : `${id}-t`} aria-label={label} onMouseDown={onMouseDown}>
      {open && (
        <div className={s.drawerInner}>
          <div className={s.drawerHead}>
            <div style={{ minWidth: 0 }}>
              <h2 id={`${id}-t`} className={s.title}>{title}</h2>
              {meta && <div className={s.desc}>{meta}</div>}
            </div>
            <div style={{ display: "flex", gap: 4, flex: "none" }}>
              {actions}
              <Button variant="ghost" size={28} iconOnly aria-label="Close" onClick={onClose}>
                <X size={16} />
              </Button>
            </div>
          </div>
          <div className={s.drawerBody}>{children}</div>
        </div>
      )}
    </dialog>
  );
}

/** Anchored panel: opens from a trigger, closes on Esc or an outside click,
 * and hands focus back to the trigger. */
export function Popover({
  trigger,
  children,
  align = "end",
  side = "bottom",
  width = 320,
  label,
}: {
  trigger: (p: { open: boolean; toggle: () => void; props: React.ButtonHTMLAttributes<HTMLButtonElement> }) => React.ReactNode;
  children: (close: () => void) => React.ReactNode;
  align?: "start" | "end";
  side?: "top" | "bottom";
  width?: number;
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const id = useId();
  const triggerId = `${id}-trigger`;
  // Focus goes back to the trigger by id, so close() never touches a ref and is safe to hand to children.
  const close = useCallback(
    (refocus = true) => {
      setOpen(false);
      if (refocus) document.getElementById(triggerId)?.focus();
    },
    [triggerId],
  );
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) close(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);
  return (
    <div ref={wrap} className={s.anchor}>
      {trigger({
        open,
        toggle: () => setOpen((o) => !o),
        props: { id: triggerId, "aria-expanded": open, "aria-controls": id, "aria-haspopup": "dialog", onClick: () => setOpen((o) => !o) },
      })}
      {open && (
        <div id={id} role="dialog" aria-label={label} className={`${s.popover} ${align === "end" ? s.alignEnd : s.alignStart} ${side === "top" ? s.sideTop : ""}`} style={{ width }}>
          {children(() => close())}
        </div>
      )}
    </div>
  );
}

export type MenuEntry =
  | { kind?: "item"; label: React.ReactNode; icon?: React.ElementType; onSelect?: () => void; href?: string; danger?: boolean }
  | { kind: "separator" }
  | { kind: "label"; label: React.ReactNode };

/** Dropdown menu: ↑/↓ move, Enter selects, Esc closes. */
export function Menu({ trigger, items, label, align = "end", side = "bottom", width = 220 }: { trigger: Parameters<typeof Popover>[0]["trigger"]; items: MenuEntry[]; label: string; align?: "start" | "end"; side?: "top" | "bottom"; width?: number }) {
  return (
    <Popover trigger={trigger} label={label} align={align} side={side} width={width}>
      {(close) => <MenuList items={items} close={close} label={label} />}
    </Popover>
  );
}

function MenuList({ items, close, label }: { items: MenuEntry[]; close: () => void; label: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.querySelector<HTMLElement>("[role=menuitem]")?.focus();
  }, []);
  const onKeyDown = (e: React.KeyboardEvent) => {
    const all = Array.from(ref.current?.querySelectorAll<HTMLElement>("[role=menuitem]") ?? []);
    const i = all.indexOf(document.activeElement as HTMLElement);
    if (e.key === "ArrowDown") all[(i + 1) % all.length]?.focus();
    else if (e.key === "ArrowUp") all[(i - 1 + all.length) % all.length]?.focus();
    else if (e.key === "Home") all[0]?.focus();
    else if (e.key === "End") all[all.length - 1]?.focus();
    else return;
    e.preventDefault();
  };
  return (
    <div ref={ref} role="menu" aria-label={label} className={s.menu} onKeyDown={onKeyDown}>
      {items.map((it, i) => {
        if (it.kind === "separator") return <div key={i} className={s.menuSep} role="separator" />;
        if (it.kind === "label") return <div key={i} className={s.menuLabel}>{it.label}</div>;
        const Icon = it.icon;
        const cls = `${s.menuItem} ${it.danger ? s.menuDanger : ""}`;
        const inner = (
          <>
            {Icon && <Icon size={16} aria-hidden="true" />}
            {it.label}
          </>
        );
        return it.href ? (
          <Link key={i} href={it.href} role="menuitem" tabIndex={-1} className={cls} onClick={close}>
            {inner}
          </Link>
        ) : (
          <button
            key={i}
            type="button"
            role="menuitem"
            tabIndex={-1}
            className={cls}
            onClick={() => {
              close();
              it.onSelect?.();
            }}
          >
            {inner}
          </button>
        );
      })}
    </div>
  );
}

/** Short explanation on hover and keyboard focus. The child must be focusable. */
export function Tooltip({ content, children, below = false }: { content: React.ReactNode; children: React.ReactElement<{ "aria-describedby"?: string }>; below?: boolean }) {
  const id = useId();
  return (
    <span className={s.tipWrap}>
      {isValidElement(children) ? cloneElement(children, { "aria-describedby": id }) : children}
      <span role="tooltip" id={id} className={`${s.tip} ${below ? s.tipBelow : ""}`}>
        {content}
      </span>
    </span>
  );
}
