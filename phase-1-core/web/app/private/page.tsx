"use client";

import Link from "next/link";
import { ChatLayout } from "@/components/ChatLayout";
import { ConversationList } from "@/components/ConversationList";
import { PlusIcon } from "@/components/Icons";
import { useApp } from "@/components/Providers";
import { Shell } from "@/components/Shell";

/** Your private clusters. */
export default function PrivateClusters() {
  const { session, ready } = useApp();
  return (
    <Shell wide>
      {ready && !session && <div className="card empty"><div className="big">Sign in to see your clusters</div><Link href="/signin" className="hint">Sign in →</Link></div>}
      {session && (
        <ChatLayout kind="cluster" base="/private">
          <div className="pane-home">
            <ConversationList kind="cluster" base="/private" empty={null} invitesOnly />
            <div className="pane-hint">
              <div className="pane-hint-icon" aria-hidden="true">💬</div>
              <h1 className="page-title">Clusters</h1>
              <p className="page-sub">Private groups with the people you choose. Only members see what is shared. Pick one on the left, or start a new one.</p>
              <Link href="/private/new" className="btn primary"><PlusIcon /> New cluster</Link>
            </div>
          </div>
        </ChatLayout>
      )}
    </Shell>
  );
}
