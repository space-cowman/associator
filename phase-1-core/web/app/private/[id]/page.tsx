"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ChatLayout } from "@/components/ChatLayout";
import { ConversationView } from "@/components/ConversationView";
import { useApp } from "@/components/Providers";
import { Shell } from "@/components/Shell";

/** One private cluster. */
export default function PrivateClusterPage() {
  const { id } = useParams<{ id: string }>();
  const { session, ready } = useApp();
  return (
    <Shell wide>
      {ready && !session && <div className="card empty"><div className="big">Sign in to open this cluster</div><Link href="/signin" className="hint">Sign in →</Link></div>}
      {session && (
        <ChatLayout kind="cluster" base="/private" activeId={id}>
          <ConversationView id={id} back="/private" />
        </ChatLayout>
      )}
    </Shell>
  );
}
