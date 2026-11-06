"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Conversation } from "@/lib/types";
import { Avatar } from "./Avatar";
import { useApp } from "./Providers";

/** Your private clusters (kind "cluster") or one-to-one chats (kind "direct"): invitations / message requests first, each with accept · decline · block. */
export function ConversationList({ kind, base, empty, compact = false, activeId, invitesOnly = false }: {
  kind: Conversation["kind"]; base: string; empty: React.ReactNode; compact?: boolean; activeId?: string; invitesOnly?: boolean;
}) {
  const { toast } = useApp();
  const [items, setItems] = useState<Conversation[] | null>(null);
  const load = useCallback(() => {
    api<Conversation[]>("/conversations")
      .then((all) => setItems(all.filter((c) => c.kind === kind)))
      .catch(() => setItems([]));
  }, [kind]);
  useEffect(load, [load]);

  /** Accept, decline or block. */
  async function act(c: Conversation, action: "accept" | "decline" | "block") {
    try {
      if (action === "block") {
        if (!c.invited_by || !confirm(`Block @${c.invited_by}? They won't be able to invite you or message you.`)) return;
        await api(`/me/blocks/${c.invited_by}`, { method: "PUT" });
        toast(`Blocked @${c.invited_by}`);
      } else {
        await api(`/conversations/${c.id}/${action}`, { method: "POST" });
      }
      load();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Something went wrong", true);
    }
  }

  if (items === null) return <div className="skeleton" style={{ height: 120 }} />;
  const invites = items.filter((c) => c.my_state === "invited");
  const active = items.filter((c) => c.my_state === "active");
  const noun = kind === "cluster" ? "Invitations" : "Message requests";

  if (compact) {
    return (
      <div className="conv-list compact">
        {invites.length > 0 && activeId && <Link href={base} className="conv-invites">{invites.length} {invites.length === 1 ? noun.toLowerCase().replace(/s$/, "") : noun.toLowerCase()}</Link>}
        {active.map((c) => (
          <Link key={c.id} href={`${base}/${c.id}`} className={`conv-row${c.id === activeId ? " active" : ""}`} aria-current={c.id === activeId ? "page" : undefined}>
            <Avatar handle={kind === "direct" ? c.title.slice(1) : c.title} size={34} />
            <div style={{ minWidth: 0 }}>
              <div className="conv-title">{c.title}</div>
              <div className="hint">{kind === "cluster" ? `${c.member_count} member${c.member_count === 1 ? "" : "s"}` : c.member_count < 2 ? "Request sent" : "Private chat"}</div>
            </div>
          </Link>
        ))}
        {active.length === 0 && <div className="hint conv-none">{kind === "cluster" ? "No clusters yet" : "No chats yet"}</div>}
      </div>
    );
  }

  return (
    <>
      {invites.length > 0 && (
        <section className="card pad stack" style={{ gap: 10 }}>
          <h2 className="section-label">{noun}</h2>
          {invites.map((c) => (
            <div key={c.id} className="row spread">
              <div className="row" style={{ gap: 10 }}>
                <Avatar handle={kind === "direct" ? c.title.slice(1) : c.invited_by} size={30} />
                <div>
                  <div style={{ fontWeight: 500 }}>{c.title}</div>
                  <div className="hint">
                    {kind === "cluster" ? `@${c.invited_by ?? "someone"} invited you` : "wants to message you"}
                  </div>
                </div>
              </div>
              <div className="row">
                <button className="btn small primary" onClick={() => act(c, "accept")}>Accept</button>
                <button className="btn small ghost" onClick={() => act(c, "decline")}>{kind === "cluster" ? "Decline" : "Ignore"}</button>
                {c.invited_by && <button className="btn small ghost danger" onClick={() => act(c, "block")}>Block</button>}
              </div>
            </div>
          ))}
        </section>
      )}
      {invitesOnly ? null : active.length === 0 && invites.length === 0 ? (
        <div className="card empty">{empty}</div>
      ) : (
        active.length > 0 && (
          <section className="card conv-list">
            {active.map((c) => (
              <Link key={c.id} href={`${base}/${c.id}`} className="conv-row">
                <Avatar handle={kind === "direct" ? c.title.slice(1) : c.title} size={36} />
                <div style={{ minWidth: 0 }}>
                  <div className="conv-title">{c.title}</div>
                  <div className="hint">
                    {kind === "cluster" ? `${c.member_count} member${c.member_count === 1 ? "" : "s"}` : c.member_count < 2 ? "Request sent" : "Private chat"}
                    {c.my_role === "admin" && kind === "cluster" ? " · admin" : ""}
                  </div>
                </div>
              </Link>
            ))}
          </section>
        )
      )}
    </>
  );
}
