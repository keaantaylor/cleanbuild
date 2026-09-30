"use client";

/* Downloads of the backend's real exports. The session cookie authenticates
   the request; the file is saved under a readable name. */

type ToastFn = (text: string, tone?: "ok" | "info" | "warn" | "err") => void;

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function fetchExport(url: string): Promise<Response> {
  const res = await fetch(url, { credentials: "include" });
  if (res.status === 401) {
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full navigation clears session state
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    throw new Error("Please sign in again.");
  }
  if (!res.ok) {
    let detail = `The export failed (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // not JSON
    }
    throw new Error(detail);
  }
  return res;
}

/** Worksheet name from a file's base name, e.g. "claims_2026_exceptions" → "Exceptions". */
function sheetName(basename: string): string {
  const last = basename.split("_").pop() ?? "Sheet1";
  return last.charAt(0).toUpperCase() + last.slice(1);
}

/** Download one of the backend's export endpoints. Tabular (CSV) exports are
 * saved as Excel workbooks; archives (the audit pack) are saved as they are. */
export async function exportFile(url: string, basename: string, toast?: ToastFn) {
  try {
    const res = await fetchExport(url);
    const ext = url.match(/\.(csv|zip)(\?|$)/)?.[1] ?? "csv";
    if (ext !== "csv") {
      saveBlob(await res.blob(), `${basename}.${ext}`);
      toast?.(`Downloaded ${basename}.${ext}`, "ok");
      return;
    }
    const csv = await res.text();
    try {
      const { csvToXlsx } = await import("./xlsx");
      saveBlob(await csvToXlsx(csv, sheetName(basename)), `${basename}.xlsx`);
      toast?.(`Downloaded ${basename}.xlsx`, "ok");
    } catch {
      // Never lose the export: fall back to the backend's CSV and say so.
      saveBlob(new Blob([csv], { type: "text/csv;charset=utf-8" }), `${basename}.csv`);
      toast?.(`Excel conversion failed, so ${basename}.csv was downloaded instead`, "warn");
    }
  } catch (e) {
    toast?.(e instanceof Error ? e.message : "The export failed.", "err");
  }
}
