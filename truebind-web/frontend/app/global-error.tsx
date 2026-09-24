"use client";

// Last-resort boundary (errors in the root layout itself). Must render its own <html>.
export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", display: "grid", placeItems: "center", minHeight: "100vh", margin: 0 }}>
        <div style={{ maxWidth: 480, padding: 24 }}>
          <h1 style={{ fontSize: 20 }}>TrueBind couldn&rsquo;t start</h1>
          <p>Something went wrong while loading the application.</p>
          <button type="button" onClick={reset} style={{ padding: "8px 14px", cursor: "pointer" }}>Try again</button>
        </div>
      </body>
    </html>
  );
}
