"use client";

import { ErrorState } from "@/components/ds";

export default function DashboardError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div style={{ maxWidth: 720 }}>
      <ErrorState title="This page couldn't be displayed" onRetry={reset}
        message="Something went wrong while showing this page. Your data is safe; try again, or go back to the overview."
        details={error.digest ? `reference ${error.digest}` : error.message} />
    </div>
  );
}
