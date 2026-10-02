import { LoadingState } from "@/components/nocturne/ui";

// Shown instantly on every navigation inside the app while the next page
// (and, in development, its first compile) is prepared.
export default function Loading() {
  return (
    <div className="flex max-w-[1200px] flex-col gap-6 px-4 pt-8 sm:px-6">
      <LoadingState label="Loading page" rows={7} />
    </div>
  );
}
