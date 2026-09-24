import { PageSkeleton } from "@/components/layout/ShellSkeleton";

// Shown instantly on every navigation inside the app while the next page
// (and, in development, its first compile) is prepared.
export default function Loading() {
  return <PageSkeleton />;
}
