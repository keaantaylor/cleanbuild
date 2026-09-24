"use client";

import { useEffect, useRef, useState } from "react";

/** Animates a displayed number toward `target` over `durationMs`. Pure
 * CSS can't animate a text node's numeric content, so this is the one
 * piece of the marketing page's motion that has to be JS -- still no
 * library, just requestAnimationFrame. Respects prefers-reduced-motion
 * by jumping straight to the target instead of counting. */
export function useCountUp(target: number, durationMs = 600): number {
  const [value, setValue] = useState(target);
  const fromRef = useRef(target);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    const reduceMotion = typeof window !== "undefined"
      && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) {
      fromRef.current = target;
      const id = requestAnimationFrame(() => setValue(target));  // async: no cascading render
      return () => cancelAnimationFrame(id);
    }

    const from = fromRef.current;
    const delta = target - from;
    if (delta === 0) return;

    const start = performance.now();
    const step = (now: number) => {
      const progress = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setValue(from + delta * eased);
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(step);
      } else {
        fromRef.current = target;
      }
    };
    frameRef.current = requestAnimationFrame(step);
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  return value;
}
