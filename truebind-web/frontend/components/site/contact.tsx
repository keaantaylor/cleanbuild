import { CalendarBlank, EnvelopeSimple, Phone } from "@phosphor-icons/react";
import { BOOK_CALL_URL, CONTACT_EMAIL, CONTACT_PHONE } from "@/lib/constants";

/** Email, phone (when configured) and a "Book a call" link, on every sales form and page. */
export function ContactLine({ className = "" }: { className?: string }) {
  return (
    <div className={`flex flex-wrap items-center gap-x-4 gap-y-2 text-[13px] ${className}`} style={{ color: "var(--muted)" }}>
      <span>Prefer to talk?</span>
      <a href={`mailto:${CONTACT_EMAIL}`} className="flex items-center gap-1.5 underline-offset-2 hover:underline" style={{ color: "var(--accentText)" }}><EnvelopeSimple />{CONTACT_EMAIL}</a>
      {CONTACT_PHONE && <a href={`tel:${CONTACT_PHONE.replace(/\s/g, "")}`} className="flex items-center gap-1.5 hover:underline" style={{ color: "var(--accentText)" }}><Phone />{CONTACT_PHONE}</a>}
      <a href={BOOK_CALL_URL} target="_blank" rel="noopener noreferrer" className="tb-btn !py-1.5 text-[13px]"><CalendarBlank />Book a call</a>
    </div>
  );
}
