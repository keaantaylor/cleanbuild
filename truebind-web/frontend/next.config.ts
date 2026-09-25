import type { NextConfig } from "next";

// Hosted deployments: the browser calls /api/v1 on the frontend's own domain
// and this rewrite forwards it to the API (TRUEBIND_API_ORIGIN, e.g.
// https://truebind-api.onrender.com). One origin means the HttpOnly session
// cookie is first-party and no cross-site CORS/cookie settings are needed.
// Local development leaves it unset and calls the API on port 8000 directly.
const apiOrigin = process.env.TRUEBIND_API_ORIGIN?.replace(/\/+$/, "");

// A Vercel build without the rewrite target ships a site whose sign-in fails
// with "Failed to fetch". Fail the build instead, unless the API is called
// directly through an absolute NEXT_PUBLIC_API_URL.
if (process.env.VERCEL && !apiOrigin && !/^https?:\/\//.test(process.env.NEXT_PUBLIC_API_URL ?? "")) {
  throw new Error(
    "TRUEBIND_API_ORIGIN is not set. Add it in Vercel → Settings → Environment Variables " +
      "(e.g. https://your-api.onrender.com) and redeploy.",
  );
}

const nextConfig: NextConfig = {
  async rewrites() {
    return apiOrigin ? [{ source: "/api/v1/:path*", destination: `${apiOrigin}/api/v1/:path*` }] : [];
  },
};

export default nextConfig;
