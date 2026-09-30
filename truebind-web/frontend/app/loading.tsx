import { Mark } from "@/components/nocturne/ui";

export default function RootLoading() {
  return (
    <div className="grid min-h-screen place-items-center" style={{ background: "var(--bg)" }}>
      <span className="animate-pulse"><Mark size={32} radius={8} /></span>
    </div>
  );
}
