"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ChatLayout } from "@/components/ChatLayout";
import { ConversationView } from "@/components/ConversationView";
import { useApp } from "@/components/Providers";
import { Shell } from "@/components/Shell";

/** One private chat. */
export default function DirectChatPage() {
  const { id } = useParams<{ id: string }>();
  const { session, ready } = useApp();
  return (
    <Shell wide>
      {ready && !session && <div className="card empty"><div className="big">Sign in to open this chat</div><Link href="/signin" className="hint">Sign in →</Link></div>}
      {session && (
        <ChatLayout kind="direct" base="/messages" activeId={id}>
          <ConversationView id={id} back="/messages" />
        </ChatLayout>
      )}
    </Shell>
  );
}
