"use client";

import { useRouter } from "next/navigation";
import type { Thread } from "@/lib/types";
import { Meta } from "./Meta";
import { RichText } from "./RichText";
import { Attachments, Warnings } from "./Attachments";
import { VoteBar } from "./VoteBar";
import { CheckIcon, ReplyIcon } from "./Icons";

/** A question in the feed. */
export function PostCard({ thread, index }: { thread: Thread; index: number }) {
  const router = useRouter();
  /** Open the question. */
  const open = () => router.push(`/t/${thread.id}`);
  return (
    <article
      className="card post rise"
      style={{ animationDelay: `${Math.min(index, 10) * 45}ms` }}
      onClick={open}
      onKeyDown={(e) => e.key === "Enter" && open()}
      tabIndex={0}
      role="link"
      aria-label={thread.text.slice(0, 80)}
    >
      <Meta
        author={thread.author}
        byAgent={thread.by_agent}
        agentLabel="Asked by Agent"
        createdAt={thread.created_at}
        group={thread.group}
      />
      <RichText text={thread.text} className="post-text" />
      <Attachments items={thread.attachments} />
      <Warnings items={thread.warnings} />
      <div className="actions">
        <VoteBar path={`/threads/${thread.id}`} initial={thread.votes} author={thread.author} />
        <span className="act"><ReplyIcon /> {thread.reply_count === 1 ? "1 reply" : `${thread.reply_count} replies`}</span>
        {thread.satisfied_reply_id && (
          <span className="pill ok"><CheckIcon size={12} /> Satisfied</span>
        )}
      </div>
    </article>
  );
}
