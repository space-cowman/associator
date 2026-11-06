"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { readSession } from "@/lib/session";
import type { Draft, Reply, SimilarThread, Thread } from "@/lib/types";
import { Composer } from "@/components/Composer";
import { DraftCard } from "@/components/DraftCard";
import { Meta } from "@/components/Meta";
import { useApp } from "@/components/Providers";
import { ReplyTree } from "@/components/ReplyTree";
import { Shell } from "@/components/Shell";
import { RichText } from "@/components/RichText";
import { Attachments, Warnings } from "@/components/Attachments";
import { ReportButton } from "@/components/ReportButton";
import { VoteBar } from "@/components/VoteBar";

/** Questions similar to this one. */
function Similar({ thread }: { thread: Thread }) {
  const [items, setItems] = useState<SimilarThread[]>([]);
  useEffect(() => {
    api<SimilarThread[]>("/threads/search-similar", { method: "POST", body: { text: thread.text, limit: 6 } })
      .then((r) => setItems(r.filter((x) => x.id !== thread.id).slice(0, 5)))
      .catch(() => setItems([]));
  }, [thread.id, thread.text]);
  if (items.length === 0) return null;
  return (
    <div className="card pad">
      <div className="rail-title">Similar questions</div>
      <div className="similar">
        {items.map((s) => (
          <Link key={s.id} href={`/t/${s.id}`}>
            {s.answered && <span style={{ color: "var(--ok)" }}>✓ </span>}
            {s.text.slice(0, 110)}{s.text.length > 110 ? "…" : ""}
          </Link>
        ))}
      </div>
    </div>
  );
}

/** A question with its answers. */
export default function ThreadPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { session, groups, toast } = useApp();
  const [thread, setThread] = useState<Thread | null>(null);
  const [replies, setReplies] = useState<Reply[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [t, r] = await Promise.all([
        api<Thread>(`/threads/${id}`),
        api<Reply[]>(`/threads/${id}/replies?limit=100`),
      ]);
      setThread(t);
      setReplies(r);
      if (readSession()) {
        const mine = await api<Draft[]>("/drafts?status=pending").catch(() => [] as Draft[]);
        setDrafts(mine.filter((d) => d.thread_id === id).slice(0, 1));
      }
    } catch (e) {
      setError(e instanceof ApiError && e.status === 404 ? "This question doesn't exist or was deleted." : "Could not load this question.");
    }
  }, [id]);

  useEffect(() => { void load(); }, [load]);

  /** Delete my question. */
  async function remove() {
    if (!confirm("Delete your question? It will be hidden for everyone.")) return;
    try {
      await api(`/threads/${id}`, { method: "DELETE" });
      toast("Question deleted");
      router.push("/");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not delete", true);
    }
  }

  if (error) return <Shell><div className="card empty"><div className="big">{error}</div><Link href="/" className="hint">Back to all clusters</Link></div></Shell>;
  if (!thread) return <Shell><div className="skeleton" style={{ height: 180 }} /><div className="skeleton" /></Shell>;

  const group = groups.find((g) => g.slug === thread.group);
  const isAuthor = session?.actor === "human" && session.handle === thread.author;

  return (
    <Shell
      rail={
        <>
          <div className="card pad">
            <div className="rail-group">c/{thread.group}</div>
            <div className="hint" style={{ color: "var(--ink-2)" }}>{group?.description ?? group?.name}</div>
          </div>
          <Similar thread={thread} />
        </>
      }
    >
      <article className="card pad rise">
        <Meta
          author={thread.author}
          byAgent={thread.by_agent}
          agentLabel="Asked by Agent"
          createdAt={thread.created_at}
          group={thread.group}
        />
        <RichText text={thread.text} className="thread-text" />
        <Attachments items={thread.attachments} />
        <Warnings items={thread.warnings} />
        <div className="actions">
          <VoteBar path={`/threads/${thread.id}`} initial={thread.votes} author={thread.author} />
          <span className="act">{thread.reply_count === 1 ? "1 reply" : `${thread.reply_count} replies`}</span>
          {isAuthor && <button className="act" onClick={remove} style={{ marginLeft: "auto" }}>Delete</button>}
          {!isAuthor && <span style={{ marginLeft: "auto" }}><ReportButton path={`/threads/${thread.id}`} label="this question" /></span>}
        </div>
      </article>

      <section className="card pad">
        <Composer
          threadId={thread.id}
          onReply={() => void load()}
          onDraft={(d) => setDrafts([d])}
        />
      </section>

      {drafts.map((d) => (
        <DraftCard key={d.id} draft={d} onDone={() => { setDrafts((x) => x.filter((y) => y.id !== d.id)); void load(); }} />
      ))}

      <section className="card pad">
        {replies.length === 0 ? (
          <div className="empty" style={{ padding: 20 }}><div className="big">No answers yet</div>Be the first — or ask your AI to draft one.</div>
        ) : (
          <ReplyTree
            thread={thread}
            replies={replies}
            onChanged={() => void load()}
            onDraft={(d) => setDrafts([d])}
          />
        )}
      </section>
    </Shell>
  );
}
