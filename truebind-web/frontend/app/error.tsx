"use client";

import { ErrorState } from "@/components/ds";

export default function RootError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div style={{ maxWidth: 640, margin: "12vh auto", padding: 24 }}>
      <ErrorState title="TrueBind couldn't load this page" onRetry={reset}
        message="An unexpected error stopped this page from rendering. Try again; if it keeps happening, reload the app."
        details={error.digest ? `reference ${error.digest}` : error.message} />
    </div>
  );
}
