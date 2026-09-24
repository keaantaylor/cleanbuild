"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/** Fetch on mount / when `key` changes, with explicit loading and error
 * states and a stable reload(). Stale responses from a previous key are
 * ignored. `pollMs` re-fetches in the background (no loading flicker). */
export function useApi<T>(fetcher: () => Promise<T>, key: unknown[] = [],
                          pollMs?: number | ((data: T | null) => number | undefined)): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const fetcherRef = useRef(fetcher);
  const dataRef = useRef<T | null>(null);
  const pollRef = useRef(pollMs);
  useEffect(() => { fetcherRef.current = fetcher; pollRef.current = pollMs; });

  const run = useCallback(async (background: boolean) => {
    const mine = ++seq.current;
    if (!background) await Promise.resolve().then(() => setLoading(true));
    try {
      const result = await fetcherRef.current();
      if (mine !== seq.current) return;
      dataRef.current = result;
      setData(result);
      setError(null);
    } catch (e) {
      if (mine !== seq.current) return;
      setError(e instanceof ApiError ? e.message : "Something went wrong while loading this data.");
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, []);

  const depKey = JSON.stringify(key);
  const polls = pollMs !== undefined;
  useEffect(() => {
    void run(false);
    if (!polls) return;
    // One ticker; a function poll interval is re-evaluated against the latest
    // data every tick (e.g. poll fast while a job runs, stop when it ends).
    let last = Date.now();
    const t = setInterval(() => {
      const p = pollRef.current;
      const every = typeof p === "function" ? p(dataRef.current) : p;
      if (!every || document.hidden || Date.now() - last < every) return;
      last = Date.now();
      void run(true);
    }, 250);
    return () => clearInterval(t);
  }, [depKey, polls, run]);

  const reload = useCallback(() => { void run(true); }, [run]);
  return { data, error, loading, reload };
}
