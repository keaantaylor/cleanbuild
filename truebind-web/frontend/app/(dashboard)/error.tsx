"use client";

import Link from "next/link";
import { ErrorState } from "@/components/nocturne/ui";

export default function DashboardError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="flex max-w-[760px] flex-col gap-3 px-4 pt-8 sm:px-6">
      <ErrorState
        title="This page couldn’t be displayed"
        message={`Something went wrong while showing this page. Your data is safe; try again, or go back to the overview.${error.digest ? ` (reference ${error.digest})` : ""}`}
        onRetry={reset}
      />
      <Link href="/overview" className="text-[13px]" style={{ color: "var(--accentText)" }}>Go to the overview →</Link>
    </div>
  );
}
