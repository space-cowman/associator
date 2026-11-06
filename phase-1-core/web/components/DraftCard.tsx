"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError, confirmPersonalData } from "@/lib/api";
import type { Draft, Thread } from "@/lib/types";
import { useApp } from "./Providers";
import { Meta } from "./Meta";
import { RichText } from "./RichText";
import { BotIcon, CheckIcon, WarnIcon } from "./Icons";

const MODE = { ask_my_ai: "Your AI", platform_ai: "Platform AI", mcp: "Your AI app (MCP)" } as const;

/** The approve screen: the draft as it will look when published, editable, Approve / Discard. */
export function DraftCard({ draft, showThread = false, onDone }: { draft: Draft; showThread?: boolean; onDone?: () => void }) {
  const { session, toast, reloadDrafts } = useApp();
  const [text, setText] = useState(draft.text);
  const [thread, setThread] = useState<Thread | null>(null);
  const [busy, setBusy] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (showThread) api<Thread>(`/threads/${draft.thread_id}`).then(setThread).catch(() => setThread(null));
  }, [showThread, draft.thread_id]);

  /** Approve, edit or discard the draft. */
  async function decide(kind: "approve" | "discard") {
    setBusy(true);
    setError("");
    try {
      const done = await confirmPersonalData((confirm) =>
        api(`/drafts/${draft.id}/${kind}`, {
          method: "POST",
          body: kind === "approve"
            ? { ...(text !== draft.text ? { text } : {}), ...(confirm ? { confirm_personal_data: true } : {}) }
            : undefined,
        }).then(() => true),
      );
      if (!done) return setBusy(false);
      toast(kind === "approve" ? "Published" : "Draft discarded");
      setLeaving(true);
      void reloadDrafts();
      setTimeout(() => onDone?.(), 420);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong");
      setBusy(false);
    }
  }

  return (
    <div className={`card pad stack${leaving ? " leaving" : " rise"}`}>
      {thread && (
        <Link href={`/t/${thread.id}`} className="hint" style={{ display: "block" }}>
          On <b>c/{thread.group}</b>: “{thread.text.slice(0, 140)}{thread.text.length > 140 ? "…" : ""}”
        </Link>
      )}
      <div className="row spread">
        <span className="pill agent"><BotIcon /> {MODE[draft.mode]}{draft.model_label ? ` · ${draft.model_label}` : ""}</span>
        <span className="hint">Waiting for your approval</span>
      </div>
      {draft.plan.length > 0 && (
        <div className="hint">Split into: {draft.plan.map((p) => `${p.kind}${p.model ? ` (${p.model})` : ""}`).join(" · ")}</div>
      )}
      {draft.memory_used.length > 0 && (
        <div className="hint">
          Used from your memory (only you see this):
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>{draft.memory_used.map((m) => <li key={m}>{m}</li>)}</ul>
        </div>
      )}
      {draft.warnings.map((w) => (
        <div className="warning" key={w} style={{ borderRadius: 8 }}><WarnIcon /> {w}</div>
      ))}
      <div className="draft-preview">
        <Meta author={session?.handle ?? null} byAgent agentLabel="Answered by Agent" createdAt={new Date().toISOString()} />
        <textarea
          className="textarea"
          value={text}
          onChange={(e) => setText(e.target.value)}
          aria-label="Draft text (you can edit it before approving)"
          style={{ marginTop: 8 }}
        />
        <div className={`counter${text.length > 500 ? " over" : ""}`}>{text.length}/500 · edit freely before approving</div>
        <div className="hint" style={{ marginTop: 6 }}>Preview</div>
        <RichText text={text} className="reply-text preview" />
      </div>
      <div className="row">
        <button className="btn primary small" disabled={busy || !text.trim() || text.length > 500} onClick={() => decide("approve")}>
          <CheckIcon /> {text !== draft.text ? "Approve edited" : "Approve"}
        </button>
        <button className="btn ghost small danger" disabled={busy} onClick={() => decide("discard")}>Discard</button>
      </div>
      {error && <div className="error">{error}</div>}
    </div>
  );
}
