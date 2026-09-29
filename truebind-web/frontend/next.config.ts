import type { NextConfig } from "next";

// Hosted deployments: the browser calls /api/v1 on the frontend's own domain
// and this rewrite forwards it to the API (TRUEBIND_API_ORIGIN, e.g.
// https://truebind-api.onrender.com). One origin means the HttpOnly session
// cookie is first-party and no cross-site CORS/cookie settings are needed.
// Local development leaves it unset and calls the API on port 8000 directly.
const apiOrigin = process.env.TRUEBIND_API_ORIGIN?.replace(/\/+$/, "");

// Browser hardening for every page (P10). Scripts are not restricted by CSP
// here because Next.js inlines its bootstrap; framing, plugins, base URLs and
// form targets are.
const SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'" },
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
  async rewrites() {
    return apiOrigin ? [{ source: "/api/v1/:path*", destination: `${apiOrigin}/api/v1/:path*` }] : [];
  },
};

export default nextConfig;
