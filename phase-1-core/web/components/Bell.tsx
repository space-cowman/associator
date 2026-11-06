"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import type { Notification } from "@/lib/types";
import { useApp } from "./Providers";
import { Avatar } from "./Avatar";

/** The bell icon. */
function BellIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
      <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
    </svg>
  );
}

/** Replies to you and Satisfied marks, with an unread count; opening marks them read. */
export function Bell() {
  const { session } = useApp();
  const [items, setItems] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const n = await api<{ unread: number; items: Notification[] }>("/me/notifications");
      setItems(n.items);
      setUnread(n.unread);
    } catch {
    }
  }, []);

  useEffect(() => {
    if (!session) return;
    void load();
    const timer = setInterval(() => void load(), 45_000);
    return () => clearInterval(timer);
  }, [session, load]);

  useEffect(() => {
    /** Close the list. */
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, []);

  /** Open or close the list. */
  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && unread > 0) {
      setUnread(0);
      await api("/me/notifications/read", { method: "POST" }).catch(() => undefined);
    }
  }

  if (!session) return null;
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button className="icon-btn" aria-label={`Notifications: ${unread} unread`} onClick={toggle}>
        <BellIcon />
        {unread > 0 && <span className="badge">{unread}</span>}
      </button>
      {open && (
        <div className="dropdown notif" role="menu">
          <div className="rail-title" style={{ padding: "6px 10px 2px" }}>Notifications</div>
          {items.length === 0 && <div className="hint" style={{ padding: "10px" }}>Nothing yet. Replies to you show up here.</div>}
          {items.map((n) => (
            <Link key={n.id} href={`/t/${n.thread_id}${n.reply_id ? `#r-${n.reply_id}` : ""}`} className={`notif-item${n.read ? "" : " unread"}`} onClick={() => setOpen(false)}>
              <Avatar handle={n.actor} size={28} />
              <span>
                <span className="notif-text">
                  <b>@{n.actor ?? "someone"}</b>{" "}
                  {n.kind === "reply" ? (n.via === "agent" ? "answered through their AI app on" : n.via === "assisted" ? "replied (assisted by their AI) on" : "replied on") : "marked your answer Satisfied on"}{" "}
                  “{n.thread_text.slice(0, 60)}{n.thread_text.length > 60 ? "…" : ""}”
                </span>
                <span className="hint">{timeAgo(n.created_at)}</span>
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
