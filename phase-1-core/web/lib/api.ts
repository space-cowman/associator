// The one way the page talks to the api: same-origin /api/* (forwarded by Next.js).
import { clearToken, getToken, saveToken } from "./session";

export class ApiError extends Error {
  constructor(public status: number, message: string, public reason?: string) {
    super(message);
  }
}

/** A readable error message from a response. */
function messageFrom(data: unknown, status: number): string {
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as { loc?: unknown[]; msg?: string } | undefined;
    const field = first?.loc?.slice(1).join(".");
    return first ? `${field ? field + ": " : ""}${first.msg ?? "invalid"}` : "Invalid request";
  }
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string; reason?: string; blocks?: { kind: string; location: string }[] };
    if (d.reason === "confirm_personal_data") return d.message ?? "This contains personal data.";
    if (d.blocks?.length) {
      const what = d.blocks.map((b) => b.kind).join(", ");
      return `${d.message ?? "Blocked"} (${what})`;
    }
    return d.message ?? d.reason ?? `Request failed (${status})`;
  }
  return status === 429 ? "Too many requests, try again later" : `Request failed (${status})`;
}

const BASE_HEADERS = { Accept: "application/json", "X-Requested-With": "platform" };

let refreshing: Promise<string | null> | null = null;

/** New 15-minute access token from the sign-in cookie (HttpOnly; scripts never see it). */
export function refreshSession(): Promise<string | null> {
  if (refreshing) return refreshing;
  /** Get a fresh sign-in token. */
  const run = async (): Promise<string | null> => {
    try {
      const res = await fetch("/api/auth/refresh", { method: "POST", headers: BASE_HEADERS, cache: "no-store" });
      if (!res.ok) return null;
      const { access_token } = (await res.json()) as { access_token: string };
      saveToken(access_token);
      return access_token;
    } catch {
      return null;
    }
  };
  const locked = (async (): Promise<string | null> =>
    typeof navigator !== "undefined" && navigator.locks ? await navigator.locks.request("pp-refresh", run) : await run())();
  const pending = locked.finally(() => { refreshing = null; });
  refreshing = pending;
  return pending;
}

/** Sign out in this tab. */
export async function endSession(): Promise<void> {
  await fetch("/api/auth/logout", { method: "POST", headers: BASE_HEADERS }).catch(() => undefined);
  clearToken();
}

/** Call the api with the sign-in token. */
export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}, retried = false): Promise<T> {
  const headers: Record<string, string> = { ...BASE_HEADERS };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`/api${path}`, {
    method: init.method ?? "GET",
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    cache: "no-store",
  });
  if (res.status === 401 && token && !retried && !path.startsWith("/auth/")) {
    if (await refreshSession()) return api<T>(path, init, true);
    clearToken();
  }
  if (res.status === 204) return undefined as T;
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const reason = (data as { detail?: { reason?: unknown } } | null)?.detail?.reason;
    throw new ApiError(res.status, messageFrom(data, res.status), typeof reason === "string" ? reason : undefined);
  }
  return data as T;
}

/** Public posts with personal data need the person's OK: ask once, then resend confirmed. */
export async function confirmPersonalData<T>(send: (confirm: boolean) => Promise<T>): Promise<T | null> {
  try {
    return await send(false);
  } catch (e) {
    if (!(e instanceof ApiError) || e.reason !== "confirm_personal_data") throw e;
    if (!window.confirm(`${e.message}\n\nEveryone will see it. Post anyway?`)) return null;
    return await send(true);
  }
}

/** A random key for safe retries. */
export function newKey(): string {
  return crypto.randomUUID().replace(/-/g, "");
}
