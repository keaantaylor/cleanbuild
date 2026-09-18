"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/** Scroll-triggered reveal, CSS-driven (see .mkt-reveal / .mkt-revealed in
 * styles/marketing.css) -- this component only toggles a class via
 * IntersectionObserver, all animation is CSS so prefers-reduced-motion
 * (handled in that stylesheet) disables it globally with no JS branching
 * needed here. No animation library: a ~20-line hook does the whole job. */
export function Reveal({
  children, className = "", delayMs = 0,
}: { children: ReactNode; className?: string; delayMs?: number }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setRevealed(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setRevealed(true);
          observer.disconnect();
        }
      },
      { threshold: 0.15, rootMargin: "0px 0px -80px 0px" },
    );
    observer.observe(el);

    // Safety net: content must never be permanently stuck invisible --
    // e.g. a below-the-fold section whose observer entry never fires
    // because of how a specific viewport/zoom/print/screenshot tool
    // resizes the page (confirmed against a full-page Playwright capture,
    // which resizes the viewport to the full document height in one
    // synchronous step that can race the observer's callback). A normal
    // scrolling visitor never notices this; it only ever makes the
    // reveal happen slightly earlier than intended in edge cases.
    const fallback = setTimeout(() => setRevealed(true), 1500);

    return () => {
      observer.disconnect();
      clearTimeout(fallback);
    };
  }, []);

  return (
    <div
      ref={ref}
      className={`mkt-reveal ${revealed ? "mkt-revealed" : ""} ${className}`}
      style={delayMs ? { transitionDelay: `${delayMs}ms` } : undefined}
    >
      {children}
    </div>
  );
}
