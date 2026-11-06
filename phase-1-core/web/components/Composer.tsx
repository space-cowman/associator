"use client";

import { useState } from "react";
import { api, ApiError, confirmPersonalData, newKey } from "@/lib/api";
import type { Draft, Reply } from "@/lib/types";
import { useApp } from "./Providers";
import { BotIcon, SparkIcon } from "./Icons";
import { Editor, LIMIT, readyIds, stillUploading, type Upload } from "./Editor";

/** One box, three ways to answer: write it yourself, or have an AI draft it (you approve later). */
export function Composer(props: {
  threadId: string;
  parentId?: string | null;
  autoFocus?: boolean;
  onReply: (r: Reply) => void;
  onDraft: (d: Draft) => void;
  onCancel?: () => void;
}) {
  const { session, toast, reloadDrafts } = useApp();
  const [text, setText] = useState("");
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [busy, setBusy] = useState<null | "self" | "ask_my_ai" | "platform_ai">(null);
  const [error, setError] = useState("");
  const [useMemory, setUseMemory] = useState(false);

  if (!session) {
    return <div className="hint">Sign in to reply or ask an AI to draft an answer.</div>;
  }

  /** Post my reply. */
  async function reply() {
    setBusy("self");
    setError("");
    try {
      const r = await confirmPersonalData((confirm) =>
        api<Reply>(`/threads/${props.threadId}/replies`, {
          method: "POST",
          body: { text, parent_id: props.parentId ?? null, attachments: readyIds(uploads), confirm_personal_data: confirm },
        }),
      );
      if (!r) return;
      setText("");
      setUploads([]);
      props.onReply(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not post");
    } finally {
      setBusy(null);
    }
  }

  /** Ask an AI for a draft. */
  async function draft(mode: "ask_my_ai" | "platform_ai") {
    if (!text.trim()) {
      setError("Tell your AI what to do first, e.g. “answer briefly” or “explain the first step”.");
      return;
    }
    setBusy(mode);
    setError("");
    try {
      const d = await api<Draft>(`/threads/${props.threadId}/drafts`, {
        method: "POST",
        body: {
          mode,
          instruction: text.trim(),
          parent_id: props.parentId ?? null,
          idempotency_key: newKey(),
          memory_on: mode === "ask_my_ai" && useMemory,
        },
      });
      setText("");
      void reloadDrafts();
      toast("Draft ready: review it below");
      props.onDraft(d);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not get a draft");
    } finally {
      setBusy(null);
    }
  }

  const over = text.length > LIMIT;
  return (
    <div className="composer">
      <Editor
        value={text}
        onChange={setText}
        uploads={uploads}
        onUploads={setUploads}
        autoFocus={props.autoFocus}
        label="Reply or AI instruction"
        placeholder="Write your answer, or tell your AI what to do (e.g. 'answer briefly with the first command to run')"
      />
      <div className="row spread">
        <div className="row">
          <button className="btn primary small" disabled={!text.trim() || over || busy !== null || stillUploading(uploads)} onClick={reply}>
            {busy === "self" ? "Posting…" : "Reply"}
          </button>
          <button className="btn small" disabled={over || busy !== null} onClick={() => draft("ask_my_ai")} title="Your own model drafts an answer; you approve it">
            <BotIcon /> {busy === "ask_my_ai" ? "Asking your AI…" : "Ask my AI"}
          </button>
          <button className="btn small" disabled={over || busy !== null} onClick={() => draft("platform_ai")} title="The platform's AI drafts an answer; you approve it">
            <SparkIcon /> {busy === "platform_ai" ? "Drafting…" : "Platform AI"}
          </button>
          {props.onCancel && <button className="btn ghost small" onClick={props.onCancel}>Cancel</button>}
        </div>
        <label className="row hint" style={{ gap: 6 }} title="Ask my AI only: the facts from Settings → My memory that match this question go to your own models. Never to Platform AI.">
          <input type="checkbox" checked={useMemory} onChange={(e) => setUseMemory(e.target.checked)} /> Use my memory
        </label>
      </div>
      {error && <div className="error">{error}</div>}
    </div>
  );
}
