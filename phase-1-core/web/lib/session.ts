// The sign-in token lives in this tab only (sessionStorage): closing the tab signs you out.
const KEY = "pp.token";

export type Session = { token: string; handle: string; actor: string; expiresAt: number };

/** The sign-in token of this tab. */
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/** The signed-in person, if the token is valid. */
export function readSession(): Session | null {
  const token = getToken();
  if (!token) return null;
  const claims = decode(token);
  if (!claims || claims.exp * 1000 < Date.now()) {
    clearToken();
    return null;
  }
  return { token, handle: claims.handle, actor: claims.act, expiresAt: claims.exp * 1000 };
}

/** Keep the sign-in token in this tab. */
export function saveToken(token: string): void {
  window.sessionStorage.setItem(KEY, token);
}

/** Forget the sign-in token. */
export function clearToken(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
  }
}

/** Read the token's public part. */
function decode(token: string): { handle: string; act: string; exp: number } | null {
  try {
    const part = token.split(".")[1];
    const json = atob(part.replace(/-/g, "+").replace(/_/g, "/"));
    const c = JSON.parse(json) as { handle?: string; act?: string; exp?: number };
    return c.handle && c.exp ? { handle: c.handle, act: c.act ?? "human", exp: c.exp } : null;
  } catch {
    return null;
  }
}
