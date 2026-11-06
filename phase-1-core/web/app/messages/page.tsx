"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Conversation } from "@/lib/types";
import { ChatLayout } from "@/components/ChatLayout";
import { ConversationList } from "@/components/ConversationList";
import { PeoplePicker } from "@/components/PeoplePicker";
import { useApp } from "@/components/Providers";
import { Shell } from "@/components/Shell";

/** Start a chat with someone. */
function NewMessage() {
  const router = useRouter();
  const { toast } = useApp();
  const [who, setWho] = useState<string[]>([]);

  /** Open or request the chat. */
  async function start() {
    try {
      const c = await api<Conversation>("/conversations/direct", { method: "POST", body: { handle: who[0] } });
      router.push(`/messages/${c.id}`);
    } catch (e) {
      toast(e instanceof ApiError && e.status === 404 ? `Can't message @${who[0]}` : "Could not start the chat", true);
    }
  }

  return (
    <section className="card pad stack" style={{ gap: 10 }}>
      <h2 className="section-label">New message</h2>
      <PeoplePicker picked={who} onChange={setWho} max={1} />
      {who.length === 1 && (
        <div className="row">
          <button className="btn small primary" onClick={start}>Message @{who[0]}</button>
          <span className="hint">They see it as a request until they accept.</span>
        </div>
      )}
    </section>
  );
}

/** Your private chats. */
export default function Messages() {
  const { session, ready } = useApp();
  return (
    <Shell wide>
      {ready && !session && <div className="card empty"><div className="big">Sign in to see your messages</div><Link href="/signin" className="hint">Sign in →</Link></div>}
      {session && (
        <ChatLayout kind="direct" base="/messages">
          <div className="pane-home">
            <ConversationList kind="direct" base="/messages" empty={null} invitesOnly />
            <div className="pane-hint">
              <div className="pane-hint-icon" aria-hidden="true">✉️</div>
              <h1 className="page-title">Messages</h1>
              <p className="page-sub">One-to-one private chats. Pick one on the left, or message someone new.</p>
              <NewMessage />
            </div>
          </div>
        </ChatLayout>
      )}
    </Shell>
  );
}
