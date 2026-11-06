import { NextResponse, type NextRequest } from "next/server";

// Content-Security-Policy with a fresh random nonce per page view: only scripts carrying it run
// (Next.js adds it to its own scripts; the layout adds it to the theme script), plus whatever
// those scripts load ('strict-dynamic'). No 'unsafe-inline' for scripts.
// Styles keep 'unsafe-inline': React style attributes cannot carry a nonce (much lower risk).
const FILES = process.env.ATTACHMENTS_ORIGIN ?? ""; // private bucket: signed uploads and file links
const DEV = process.env.NODE_ENV === "development";

function policy(nonce: string, host: string): string {
  const live = host ? `wss://${host}` : ""; // private chats' live notices (older Safari needs it named)
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${DEV ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: ${FILES}`.trim(),
    `media-src 'self' blob: ${FILES}`.trim(),
    "font-src 'self'",
    `connect-src 'self' ${live} ${FILES}${DEV ? " ws: wss:" : ""}`.replace(/\s+/g, " ").trim(),
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

export function proxy(request: NextRequest) {
  const bytes = new Uint8Array(18);
  crypto.getRandomValues(bytes);
  const nonce = btoa(String.fromCharCode(...bytes));
  // The browser's own host (behind Traefik nextUrl is the pod address); anything odd is left out.
  const header = request.headers.get("host") ?? "";
  const host = /^[a-z0-9.-]+(:\d+)?$/i.test(header) ? header : "";
  const csp = policy(nonce, host);
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp); // Next.js reads the nonce from here
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    {
      // Pages only: not static files, icons or the logo (they need no policy).
      source: "/((?!_next/static|_next/image|brand/|icon.png|apple-icon.png|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
