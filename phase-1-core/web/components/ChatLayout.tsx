"use client";

import Link from "next/link";
import type { Conversation } from "@/lib/types";
import { ConversationList } from "./ConversationList";
import { PlusIcon } from "./Icons";

/** Messaging layout: your chats on the left, the open chat filling the rest. */
export function ChatLayout({ kind, base, activeId, children }: { kind: Conversation["kind"]; base: string; activeId?: string; children: React.ReactNode }) {
  const cluster = kind === "cluster";
  return (
    <div className={`chat-layout${activeId ? "" : " index"}`}>
      <aside className="chat-side" aria-label={cluster ? "Your clusters" : "Your chats"}>
        <div className="chat-side-head">
          <Link href={base}>{cluster ? "Clusters" : "Messages"}</Link>
          <Link href={cluster ? "/private/new" : base} className="icon-btn" aria-label={cluster ? "New cluster" : "New message"} title={cluster ? "New cluster" : "New message"}>
            <PlusIcon />
          </Link>
        </div>
        <ConversationList kind={kind} base={base} compact activeId={activeId} empty={null} />
      </aside>
      {children}
    </div>
  );
}
