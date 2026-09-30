import Link from "next/link";
import { Brand } from "@/components/nocturne/ui";

export default function NotFound() {
  return (
    <div className="min-h-screen px-4" style={{ background: "var(--bg)", color: "var(--text)" }}>
      <div className="mx-auto flex max-w-[560px] flex-col gap-4 pt-[14vh]">
        <Link href="/" className="text-[15px]"><Brand size={26} /></Link>
        <span className="kicker">Not found</span>
        <h1 className="m-0 text-[30px] font-medium tracking-[-0.02em]">This page doesn’t exist</h1>
        <p className="m-0 text-[14.5px]" style={{ color: "var(--muted)" }}>The link may be out of date, or the report may have been deleted or expired.</p>
        <div className="flex gap-2">
          <Link href="/overview" className="tb-btn tb-btn-solid">Go to the overview</Link>
          <Link href="/" className="tb-btn">Home</Link>
        </div>
      </div>
    </div>
  );
}
