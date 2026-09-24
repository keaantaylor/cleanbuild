import type { NextConfig } from "next";

// Hosted deployments: the browser calls /api/v1 on the frontend's own domain
// and this rewrite forwards it to the API (TRUEBIND_API_ORIGIN, e.g.
// https://truebind-api.onrender.com). One origin means the HttpOnly session
// cookie is first-party and no cross-site CORS/cookie settings are needed.
// Local development leaves it unset and calls the API on port 8000 directly.
const apiOrigin = process.env.TRUEBIND_API_ORIGIN?.replace(/\/+$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return apiOrigin ? [{ source: "/api/v1/:path*", destination: `${apiOrigin}/api/v1/:path*` }] : [];
  },
};

export default nextConfig;
