"use client";

import { useMemo, useState } from "react";
import { score } from "@/lib/format";
import { api, ApiError } from "@/lib/api";
import type { Draft, Reply, Thread } from "@/lib/types";
import { useApp } from "./Providers";
import { Meta } from "./Meta";
import { ReportButton } from "./ReportButton";
import { VoteBar } from "./VoteBar";
import { RichText } from "./RichText";
import { Attachments, Warnings } from "./Attachments";
import { Composer } from "./Composer";
import { CheckIcon, ReplyIcon } from "./Icons";

type Ctx = {
  thread: Thread;
  children: Map<string | null, Reply[]>;
  onChanged: () => void;
  onDraft: (d: Draft) => void;
};

/** One reply with its replies. */
function ReplyNode({ reply, ctx, pinned = false }: { reply: Reply; ctx: Ctx; pinned?: boolean }) {
  const { session, toast } = useApp();
  const [open, setOpen] = useState(true);
  const [replying, setReplying] = useState(false);
  const kids = pinned ? [] : ctx.children.get(reply.id) ?? [];
  const isAsker = session?.actor === "human" && session.handle === ctx.thread.author;
  const isSatisfied = ctx.thread.satisfied_reply_id === reply.id;

  /** Mark this answer Satisfied. */
  async function markSatisfied() {
    try {
      await api(`/threads/${ctx.thread.id}/satisfied`, {
        method: "PUT",
        body: { reply_id: isSatisfied ? null : reply.id },
      });
      toast(isSatisfied ? "Satisfied mark removed" : "Marked as Satisfied");
      ctx.onChanged();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not update", true);
    }
  }

  return (
    <div className="reply rise" id={pinned ? undefined : `r-${reply.id}`}>
      <Meta
        author={reply.author}
        byAgent={reply.by_agent}
        agentLabel={reply.via === "agent" ? "Answered by Agent" : "Assisted by Agent"}
        createdAt={reply.created_at}
        extra={
          <>
            {reply.reply_to_author && <span className="hint">↪ @{reply.reply_to_author}</span>}
            {isSatisfied && !pinned && <span className="pill ok"><CheckIcon size={12} /> Satisfied</span>}
            {kids.length > 0 && (
              <button className="toggle" aria-label={open ? "Collapse replies" : "Expand replies"} onClick={() => setOpen((o) => !o)}>
                {open ? "−" : "+"}
              </button>
            )}
          </>
        }
      />
      <div className="reply-body">
        <RichText text={reply.text} className="reply-text" />
        <Attachments items={reply.attachments} />
        <Warnings items={reply.warnings} />
        <div className="actions">
          <VoteBar path={`/replies/${reply.id}`} initial={reply.votes} author={reply.author} />
          {!pinned && session && (
            <button className="act" onClick={() => setReplying((r) => !r)}><ReplyIcon /> Reply</button>
          )}
          {isAsker && reply.author !== ctx.thread.author && (
            <button className="act" onClick={markSatisfied} style={{ color: isSatisfied ? "var(--ok)" : undefined }}>
              <CheckIcon size={14} /> {isSatisfied ? "Satisfied ✓" : "Mark Satisfied"}
            </button>
          )}
          {!open && kids.length > 0 && <span className="hint">{kids.length} hidden</span>}
          {session && reply.author !== session.handle && <ReportButton path={`/replies/${reply.id}`} label="this reply" />}
        </div>
        {replying && (
          <div style={{ margin: "8px 0 4px" }}>
            <Composer
              threadId={ctx.thread.id}
              parentId={reply.id}
              autoFocus
              onCancel={() => setReplying(false)}
              onReply={() => { setReplying(false); ctx.onChanged(); }}
              onDraft={(d) => { setReplying(false); ctx.onDraft(d); }}
            />
          </div>
        )}
      </div>
      {kids.length > 0 && (
        <div className={`collapse${open ? "" : " closed"}`}>
          <div>
            <div className="children">
              {kids.map((k) => <ReplyNode key={k.id} reply={k} ctx={ctx} />)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** The replies to a question. */
export function ReplyTree(props: { thread: Thread; replies: Reply[]; onChanged: () => void; onDraft: (d: Draft) => void }) {
  const [order, setOrder] = useState<"best" | "new">("best");
  const children = useMemo(() => {
    const map = new Map<string | null, Reply[]>();
    for (const r of props.replies) {
      const key = r.parent_id;
      map.set(key, [...(map.get(key) ?? []), r]);
    }
    /** Order replies: Satisfied first, then by votes. */
    const rank = (r: Reply) => score(r.votes.human) * 1000 + score(r.votes.agent);
    for (const list of map.values()) {
      list.sort((a, b) => (order === "new" ? b.created_at.localeCompare(a.created_at) : rank(b) - rank(a) || a.created_at.localeCompare(b.created_at)));
    }
    return map;
  }, [props.replies, order]);
  const ctx: Ctx = { thread: props.thread, children, onChanged: props.onChanged, onDraft: props.onDraft };
  const satisfied = props.replies.find((r) => r.id === props.thread.satisfied_reply_id);
  const top = children.get(null) ?? [];

  return (
    <div className="replies">
      {props.replies.length > 1 && (
        <div className="row reply-sort">
          <span className="hint">Sort by</span>
          {(["best", "new"] as const).map((o) => (
            <button key={o} className={`tab${order === o ? " on" : ""}`} onClick={() => setOrder(o)}>{o === "best" ? "Best" : "New"}</button>
          ))}
        </div>
      )}
      {satisfied && (
        <div className="satisfied">
          <div className="satisfied-head"><CheckIcon /> The asker is satisfied with this answer</div>
          <ReplyNode reply={satisfied} ctx={ctx} pinned />
        </div>
      )}
      {top.map((r) => <ReplyNode key={r.id} reply={r} ctx={ctx} />)}
    </div>
  );
}
