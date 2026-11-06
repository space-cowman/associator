"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { ConversationDetail } from "@/lib/types";
import { Avatar } from "./Avatar";
import { ChatDetails } from "./ChatDetails";
import { ChatPanel } from "./ChatPanel";
import { BackIcon, FlagIcon, InfoIcon, MoreIcon } from "./Icons";
import { Menu } from "./Menu";
import { useApp } from "./Providers";

/** One private cluster or one-to-one chat: a slim header (details, report, leave), the messages (ChatPanel) and the slide-in details panel. */
export function ConversationView({ id, back }: { id: string; back: string }) {
  const { toast } = useApp();
  const router = useRouter();
  const [c, setC] = useState<ConversationDetail | null | undefined>(undefined);
  const [details, setDetails] = useState(false);
  const [reporting, setReporting] = useState(false);

  const load = useCallback(() => {
    api<ConversationDetail>(`/conversations/${id}`)
      .then(setC)
      .catch(() => setC(null));
  }, [id]);
  useEffect(load, [load]);

  /** Run an action, then reload the chat. */
  async function run(fn: () => Promise<unknown>, done?: string) {
    try {
      await fn();
      if (done) toast(done);
      load();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Something went wrong", true);
    }
  }

  if (c === undefined) return <div className="skeleton" style={{ height: 200 }} />;
  if (c === null) {
    return <div className="card empty"><div className="big">Not found</div><Link href={back} className="hint">← Back</Link></div>;
  }

  const cluster = c.kind === "cluster";

  if (c.my_state === "invited") {
    return (
      <div className="card pad stack rise">
        <h1 className="page-title">{c.title}</h1>
        <p className="page-sub">
          {cluster ? `@${c.invited_by} invited you to this private cluster.` : `${c.title} wants to message you.`}
        </p>
        <div className="row">
          <button className="btn primary" onClick={() => run(() => api(`/conversations/${id}/accept`, { method: "POST" }))}>Accept</button>
          <button className="btn ghost" onClick={() => run(async () => { await api(`/conversations/${id}/decline`, { method: "POST" }); router.push(back); })}>
            {cluster ? "Decline" : "Ignore"}
          </button>
        </div>
      </div>
    );
  }

  const active = c.members.filter((m) => m.state === "active");
  const invited = c.members.filter((m) => m.state === "invited");
  const title = c.title;
  const other = title.slice(1);
  const sub = cluster
    ? `${active.length} member${active.length === 1 ? "" : "s"}${invited.length ? ` · ${invited.length} invited` : ""} · AI ${c.ai_enabled ? "on" : "off"}`
    : active.length < 2 ? "Waiting for them to accept" : "Private chat";

  /** Leave the chat. */
  function leave() {
    if (!confirm(cluster ? `Leave ${title}?` : "Leave this chat?")) return;
    void run(async () => { await api(`/conversations/${id}/leave`, { method: "POST" }); router.push(back); });
  }
  /** Block the other person. */
  function block() {
    if (!confirm(`Block @${other}? They won't be able to invite you or message you.`)) return;
    void run(() => api(`/me/blocks/${other}`, { method: "PUT" }), `Blocked @${other}`);
  }

  return (
    <div className="chat-screen">
      <header className="chat-head">
        <Link href={back} className="icon-btn chat-back" aria-label={cluster ? "Back to clusters" : "Back to messages"}><BackIcon /></Link>
        <button type="button" className="chat-head-main" onClick={() => setDetails(true)} aria-label="Open details">
          <Avatar handle={cluster ? title : other} size={36} />
          <span className="chat-head-text">
            <span className="chat-title">{title}</span>
            <span className="chat-sub">{sub}</span>
          </span>
        </button>
        <button type="button" className="icon-btn" aria-label="Details" title="Details" onClick={() => setDetails(true)}><InfoIcon /></button>
        <Menu label="More" icon={<MoreIcon />} items={[
          { label: "Report messages", icon: <FlagIcon />, onSelect: () => setReporting(true) },
          ...(cluster ? [] : [{ label: `Block @${other}`, danger: true, onSelect: block }]),
          { label: cluster ? "Leave cluster" : "Leave chat", danger: true, onSelect: leave },
        ]} />
      </header>
      <ChatPanel
        conversationId={id}
        aiEnabled={c.ai_enabled}
        aiSharing={cluster && c.ai_sharing}
        people={active.map((m) => m.handle)}
        reporting={reporting}
        onReporting={setReporting}
      />
      <ChatDetails c={c} id={id} open={details} onClose={() => setDetails(false)} run={run} onLeave={leave} />
    </div>
  );
}
