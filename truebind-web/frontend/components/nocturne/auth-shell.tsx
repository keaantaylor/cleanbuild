"use client";

import Link from "next/link";
import { Check, ShieldCheck } from "@phosphor-icons/react";
import { Brand, ThemeToggle } from "./ui";

export type ShellStep = { key: string; label: string };

/** Two-pane layout shared by sign-in, onboarding and invitations: the dark
 * brand rail (with the step list during onboarding) and the form column. */
export function AuthShell({
  steps,
  step = -1,
  onJump,
  intro,
  headerRight,
  children,
}: {
  steps?: ShellStep[];
  step?: number;
  onJump?: (i: number) => void;
  intro?: { kicker: string; body: string };
  headerRight?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] min-h-screen lg:grid-cols-[300px_minmax(0,1fr)]" style={{ background: "var(--bg)" }}>
      <aside className="relative hidden flex-col gap-8 overflow-hidden px-7 py-7 lg:flex" style={{ background: "var(--chrome)", color: "var(--chromeText)", boxShadow: "1px 0 0 var(--chromeLine)" }}>
        <Link href="/" className="relative text-[15px]" style={{ color: "var(--chromeStrong)" }}>
          <Brand size={26} />
        </Link>
        {steps && step >= 0 ? (
          <ol className="relative m-0 flex list-none flex-col gap-1 p-0">
            {steps.map((st, i) => {
              const done = i < step,
                on = i === step;
              return (
                <li key={st.key}>
                  <button
                    type="button"
                    onClick={() => onJump?.(i)}
                    disabled={!done || !onJump}
                    className="flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-left text-[13.5px] transition-colors enabled:cursor-pointer enabled:hover:bg-[rgba(233,233,237,.05)]"
                    style={{ background: on ? "rgba(52,211,153,.14)" : "transparent", boxShadow: on ? "inset 2px 0 0 var(--accent)" : "none", color: on ? "var(--chromeStrong)" : done ? "var(--chromeText)" : "var(--chromeFaint)" }}
                  >
                    <span className="tnum grid h-[22px] w-[22px] flex-none place-items-center rounded-full text-[11px]" style={{ boxShadow: done ? "none" : `inset 0 0 0 1px ${on ? "var(--accent)" : "var(--chromeLine)"}`, background: done ? "var(--ok)" : "transparent", color: done ? "#fff" : "inherit" }}>
                      {done ? <Check size={12} weight="bold" /> : i + 1}
                    </span>
                    {st.label}
                  </button>
                </li>
              );
            })}
          </ol>
        ) : (
          intro && (
            <div className="relative flex flex-col gap-3 text-[13.5px] leading-[1.6]" style={{ color: "var(--chromeMuted)" }}>
              <span className="text-[12px] font-medium uppercase tracking-[.1em]" style={{ color: "var(--kicker)" }}>{intro.kicker}</span>
              {intro.body}
            </div>
          )
        )}
        <div className="relative mt-auto flex flex-col gap-2 text-[12px] leading-[1.5]" style={{ color: "var(--chromeFaint)" }}>
          <span className="flex items-center gap-2" style={{ color: "var(--ok)" }}>
            <ShieldCheck size={14} />
            Source files never rewritten · deleted after 30 days by default
          </span>
        </div>
      </aside>
      <main className="flex min-w-0 flex-col">
        <header className="tb-safe-top sticky top-0 z-10 flex min-h-14 items-center gap-3 px-4 sm:px-8" style={{ background: "color-mix(in srgb, var(--bg) 82%, transparent)", boxShadow: "0 1px 0 var(--line)" }}>
          <Link href="/" className="tb-hit py-2 text-[14px] lg:hidden">
            <Brand size={22} />
          </Link>
          {steps && step >= 0 && (
            <>
              <span className="tnum text-[12.5px]" style={{ color: "var(--muted)" }}>
                Step {step + 1} of {steps.length}
              </span>
              <div className="hidden h-1 w-40 overflow-hidden rounded-full sm:block" style={{ background: "var(--line)" }}>
                <div className="h-full rounded-full transition-all duration-200" style={{ width: `${((step + 1) / steps.length) * 100}%`, background: "var(--accent)" }} />
              </div>
            </>
          )}
          <div className="flex-1" />
          <ThemeToggle />
          {headerRight}
        </header>
        <div className="mx-auto w-full max-w-[720px] px-5 pb-20 pt-10 sm:px-8 sm:pt-14">{children}</div>
      </main>
    </div>
  );
}

export function Field({ label, id, children, hint }: { label: string; id: string; children: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <div>
      <label className="tb-label" htmlFor={id}>{label}</label>
      {children}
      {hint && <span className="mt-1.5 block text-[12px]" style={{ color: "var(--faint)" }}>{hint}</span>}
    </div>
  );
}

export function FormError({ children }: { children: React.ReactNode }) {
  return (
    <div role="alert" className="rounded-md px-3.5 py-2.5 text-[13px]" style={{ background: "var(--errT)", color: "var(--err)" }}>
      {children}
    </div>
  );
}
