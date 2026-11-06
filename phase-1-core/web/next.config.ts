import type { NextConfig } from "next";

// The browser only ever talks to this site; /api/* is forwarded to the api server-side,
// so there is no cross-origin access to configure and the api address never reaches the page.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:18000";
// The private attachments bucket: browsers upload to it with signed forms and load files from
// it through short-lived signed links (Terraform output attachments_origin).
const FILES = process.env.ATTACHMENTS_ORIGIN ?? "";

// The Content-Security-Policy is set per request with a nonce in proxy.ts.

const config: NextConfig = {
  output: "standalone", // small production image: only the files the server needs
  // Baked in at build time for proxy.ts (the server has no runtime environment for it).
  env: { ATTACHMENTS_ORIGIN: FILES },
  poweredByHeader: false,
  reactStrictMode: true,
  // Old links from before groups were renamed clusters.
  async redirects() {
    return [
      { source: "/g/:slug", destination: "/c/:slug", permanent: true },
      { source: "/groups", destination: "/clusters", permanent: true },
      { source: "/groups/new", destination: "/clusters/new", permanent: true },
    ];
  },
  // Local development only: in production Traefik sends /api to the api, and anything it does not
  // route (e.g. /api/readyz) must end here as a plain 404, never be forwarded.
  async rewrites() {
    return process.env.NODE_ENV === "production" ? [] : [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default config;
