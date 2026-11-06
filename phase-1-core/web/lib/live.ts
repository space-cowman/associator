// Live notices for private chats: one WebSocket per tab to /api/chat/ws.
import { refreshSession } from "@/lib/api";
import { getToken, readSession } from "@/lib/session";

export type Notice = { type: "message" | "members"; conversation_id: string };
type Listener = (n: Notice) => void;

const listeners = new Set<Listener>();
let socket: WebSocket | null = null;
let retry = 0;
let timer: ReturnType<typeof setTimeout> | null = null;

/** Open the live socket. */
async function connect(): Promise<void> {
  if (socket || listeners.size === 0) return;
  const token = readSession() ? getToken() : await refreshSession();
  if (!token) return;
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/chat/ws`);
  socket = ws;
  ws.onopen = () => ws.send(JSON.stringify({ token }));
  ws.onmessage = (ev) => {
    try {
      const data = JSON.parse(String(ev.data)) as { type: string; conversation_id?: string };
      if (data.type === "ready") retry = 0;
      if ((data.type === "message" || data.type === "members") && data.conversation_id) {
        listeners.forEach((l) => l(data as Notice));
      }
    } catch {
    }
  };
  ws.onclose = (ev) => {
    socket = null;
    if (listeners.size === 0) return;
    const expired = ev.code === 4401;
    const wait = expired ? 0 : Math.min(30_000, 1000 * 2 ** retry++);
    timer = setTimeout(async () => {
      timer = null;
      if (expired) await refreshSession();
      void connect();
    }, wait);
  };
}

/** Listen for notices while mounted; returns the unsubscribe function. */
export function listen(l: Listener): () => void {
  listeners.add(l);
  void connect();
  return () => {
    listeners.delete(l);
    if (listeners.size === 0) {
      if (timer) clearTimeout(timer);
      timer = null;
      socket?.close();
      socket = null;
    }
  };
}
