"use client";

import { ErrorState } from "@/components/nocturne/ui";

export default function RootError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="min-h-screen px-4 pt-[14vh]" style={{ background: "var(--bg)" }}>
      <div className="mx-auto max-w-[640px]">
        <ErrorState
          title="TrueBind couldn’t load this page"
          message={`An unexpected error stopped this page from rendering. Try again; if it keeps happening, reload the app.${error.digest ? ` (reference ${error.digest})` : ""}`}
          onRetry={reset}
        />
      </div>
    </div>
  );
}
