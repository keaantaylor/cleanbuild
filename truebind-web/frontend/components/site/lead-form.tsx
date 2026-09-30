"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { createPortal } from "react-dom";
import { CheckCircle } from "@phosphor-icons/react";
import { Modal } from "@/components/nocturne/ui";

type Kind = "demo" | "health";

const COPY: Record<Kind, { kicker: string; title: string; intro: string; submit: string }> = {
  demo: {
    kicker: "Book a demo",
    title: "See TrueBind on your own files",
    intro: "Tell us a little about your team and we’ll arrange a walkthrough.",
    submit: "Request a demo",
  },
  health: {
    kicker: "Bordereau Health Check",
    title: "Run a Health Check on a real bordereau",
    intro: "Tell us who you are and we’ll set up a Health Check on one of your files.",
    submit: "Request a Health Check",
  },
};

/**
 * A button that opens the demo / Health Check request form.
 * The request is not sent anywhere yet: no inbox is connected to the site,
 * so the form only confirms on screen. Connect a destination in `submit`.
 */
export function LeadButton({ kind, className, style, children }: { kind: Kind; className?: string; style?: React.CSSProperties; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className={`cursor-pointer ${className ?? ""}`} style={style} onClick={() => setOpen(true)}>
        {children}
      </button>
      {/* Portalled: the nav pill's backdrop blur would otherwise trap a fixed dialog inside it. */}
      {open && createPortal(<LeadForm kind={kind} onClose={() => setOpen(false)} />, document.body)}
    </>
  );
}

function LeadForm({ kind, onClose }: { kind: Kind; onClose: () => void }) {
  const c = COPY[kind];
  const [sent, setSent] = useState(false);
  const [f, setF] = useState({ name: "", email: "", company: "", note: "" });
  const close = useCallback(() => onClose(), [onClose]);
  const valid = f.name.trim().length > 1 && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email.trim()) && f.company.trim().length > 1;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setSent(true);
  };

  if (sent)
    return (
      <Modal open onClose={close} title="Thank you" kicker={c.kicker} actions={<button type="button" className="tb-btn tb-btn-solid" data-autofocus onClick={close}>Close</button>}>
        <div className="flex flex-col items-start gap-3">
          <span className="flex items-center gap-2 text-[15px] font-medium" style={{ color: "var(--ok)" }}>
            <CheckCircle size={20} />
            We’ll be in touch.
          </span>
          <span>
            Want to start now? You can{" "}
            <Link href="/onboarding" className="underline" style={{ color: "var(--accentText)" }}>set up your workspace</Link> and run your first bordereau yourself in about five minutes.
          </span>
        </div>
      </Modal>
    );

  return (
    <Modal open onClose={close} title={c.title} kicker={c.kicker} width={520}>
      <form className="flex flex-col gap-4" onSubmit={submit} aria-label={c.kicker}>
        <span>{c.intro}</span>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="tb-label" htmlFor={`lf-name-${kind}`}>Full name</label>
            <input id={`lf-name-${kind}`} className="tb-input" autoComplete="name" required maxLength={200} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </div>
          <div>
            <label className="tb-label" htmlFor={`lf-company-${kind}`}>Company</label>
            <input id={`lf-company-${kind}`} className="tb-input" autoComplete="organization" required maxLength={200} value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} />
          </div>
        </div>
        <div>
          <label className="tb-label" htmlFor={`lf-email-${kind}`}>Work email</label>
          <input id={`lf-email-${kind}`} className="tb-input" type="email" autoComplete="email" required maxLength={320} value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        </div>
        <div>
          <label className="tb-label" htmlFor={`lf-note-${kind}`}>{kind === "health" ? "About the bordereau (optional)" : "Anything we should know? (optional)"}</label>
          <textarea id={`lf-note-${kind}`} className="tb-input min-h-[84px]" maxLength={2000} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder={kind === "health" ? "e.g. monthly claims bordereau from a TPA, about 2,000 rows" : ""} />
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
          <button type="button" className="tb-btn tb-btn-ghost" onClick={close}>Cancel</button>
          <button type="submit" className="tb-btn tb-btn-solid" disabled={!valid}>{c.submit}</button>
        </div>
      </form>
    </Modal>
  );
}
