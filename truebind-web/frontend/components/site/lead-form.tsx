"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { createPortal } from "react-dom";
import { CheckCircle } from "@phosphor-icons/react";
import { Modal } from "@/components/nocturne/ui";
import { API_BASE } from "@/lib/api";
import { CONTACT_EMAIL } from "@/lib/constants";
import { ContactLine } from "./contact";

type Kind = "demo" | "health";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = ".xlsx,.xls,.csv";

const COPY: Record<Kind, { kicker: string; title: string; intro: string; submit: string; done: string }> = {
  demo: {
    kicker: "Book a demo",
    title: "See TrueBind on your own files",
    intro: "Tell us a little about your team and we’ll arrange a walkthrough.",
    submit: "Request a demo",
    done: "We’ll be in touch within one working day.",
  },
  health: {
    kicker: "Free Health Check",
    title: "Send one bordereau. Get it back checked.",
    intro: "Founding pilot: your first file is free. Within one working day we send back the Health Check, your workbook annotated cell by cell, a corrected copy of the safe fixes and a query letter for the sender.",
    submit: "Send for a Health Check",
    done: "Your file has arrived safely. We’ll send the Health Check within one working day.",
  },
};

/** A button that opens the demo / Health Check request form. Requests go to
 * the API (POST /leads, or /leads/health-check with the file); the API stores
 * them first and then emails the notification address. */
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [f, setF] = useState({ name: "", email: "", company: "", note: "", website: "" });
  const [file, setFile] = useState<File | null>(null);
  const [consent, setConsent] = useState(false);
  const close = useCallback(() => onClose(), [onClose]);
  const fileProblem = file && file.size > MAX_BYTES ? "The file is larger than 10 MB. Send a smaller extract." : file && !/\.(xlsx|xls|csv)$/i.test(file.name) ? "Send an .xlsx, .xls or .csv file." : null;
  const valid = f.name.trim().length > 1 && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email.trim()) && f.company.trim().length > 1 && (kind === "demo" || (file && !fileProblem && consent));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    try {
      let res: Response;
      const page = typeof window !== "undefined" ? window.location.pathname : "/";
      if (kind === "health" && file) {
        const body = new FormData();
        for (const [k, v] of Object.entries({ ...f, page, consent: String(consent) })) body.append(k, v);
        body.append("file", file);
        res = await fetch(`${API_BASE}/leads/health-check`, { method: "POST", body });
      } else {
        res = await fetch(`${API_BASE}/leads`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind, ...f, page }) });
      }
      if (!res.ok) {
        let detail = `Something went wrong. Please email ${CONTACT_EMAIL} instead.`;
        try {
          const j = await res.json();
          if (typeof j.detail === "string") detail = j.detail;
        } catch {
          // not JSON
        }
        if (res.status === 429) detail = `Too many requests from this network. Please try again in an hour, or email ${CONTACT_EMAIL}.`;
        setError(detail);
        return;
      }
      setSent(true);
    } catch {
      setError(`We couldn’t reach TrueBind. Check your connection, or email ${CONTACT_EMAIL}.`);
    } finally {
      setBusy(false);
    }
  };

  if (sent)
    return (
      <Modal open onClose={close} title="Thank you" kicker={c.kicker} actions={<button type="button" className="tb-btn tb-btn-solid" data-autofocus onClick={close}>Close</button>}>
        <div className="flex flex-col items-start gap-3">
          <span className="flex items-center gap-2 text-[15px] font-medium" style={{ color: "var(--ok)" }}>
            <CheckCircle size={20} />
            {c.done}
          </span>
          <span>
            Want to start now? You can{" "}
            <Link href="/onboarding" className="underline" style={{ color: "var(--accentText)" }}>set up your workspace</Link> and run your first bordereau yourself in about five minutes.
          </span>
        </div>
      </Modal>
    );

  return (
    <Modal open onClose={close} title={c.title} kicker={c.kicker} width={540}>
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
        {kind === "health" && (
          <div>
            <label className="tb-label" htmlFor="lf-file">Your bordereau (.xlsx, .xls or .csv, up to 10 MB)</label>
            <input id="lf-file" className="tb-input" type="file" accept={ACCEPT} required onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            {fileProblem && <span className="mt-1 block text-[12.5px]" style={{ color: "var(--err)" }}>{fileProblem}</span>}
          </div>
        )}
        <div>
          <label className="tb-label" htmlFor={`lf-note-${kind}`}>{kind === "health" ? "Anything we should know? (optional)" : "Anything we should know? (optional)"}</label>
          <textarea id={`lf-note-${kind}`} className="tb-input min-h-[72px]" maxLength={2000} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder={kind === "health" ? "e.g. monthly claims bordereau for a Lloyd’s syndicate, about 2,000 rows" : ""} />
        </div>
        {/* Honeypot: hidden from people; bots fill it in. */}
        <input type="text" name="website" tabIndex={-1} autoComplete="off" aria-hidden="true" className="absolute -left-[9999px] h-0 w-0 opacity-0" value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} />
        {kind === "health" && (
          <label className="flex items-start gap-2.5 text-[13px] leading-[1.5]">
            <input type="checkbox" className="mt-[3px]" checked={consent} onChange={(e) => setConsent(e.target.checked)} required />
            <span>
              I’m allowed to share this file, and I agree TrueBind may read it to prepare my Health Check. It is stored securely, used for nothing else and deleted after 30 days. See the{" "}
              <Link href="/security" className="underline" style={{ color: "var(--accentText)" }} target="_blank">security page</Link>.
            </span>
          </label>
        )}
        <ContactLine className="pt-1" />
        {error && <span role="alert" className="text-[13px]" style={{ color: "var(--err)" }}>{error}</span>}
        <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
          <button type="button" className="tb-btn tb-btn-ghost" onClick={close}>Cancel</button>
          <button type="submit" className="tb-btn tb-btn-solid" disabled={!valid || busy}>{busy ? "Sending…" : c.submit}</button>
        </div>
      </form>
    </Modal>
  );
}
