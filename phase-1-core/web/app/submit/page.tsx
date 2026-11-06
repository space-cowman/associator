"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, ApiError, confirmPersonalData } from "@/lib/api";
import type { SimilarThread, Thread } from "@/lib/types";
import { Editor, LIMIT, readyIds, stillUploading, type Upload } from "@/components/Editor";
import { useApp } from "@/components/Providers";
import { RichText } from "@/components/RichText";
import { Shell } from "@/components/Shell";

/** The form to ask a question. */
function SubmitForm() {
  const params = useSearchParams();
  const router = useRouter();
  const { session, groups } = useApp();
  const [group, setGroup] = useState(params.get("group") ?? "");
  const [text, setText] = useState("");
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [similar, setSimilar] = useState<SimilarThread[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!group && groups[0]) setGroup(groups[0].slug);
  }, [groups, group]);

  useEffect(() => {
    if (text.trim().length < 12) return setSimilar([]);
    const timer = setTimeout(() => {
      api<SimilarThread[]>("/threads/search-similar", { method: "POST", body: { text: text.slice(0, LIMIT), limit: 5 } })
        .then(setSimilar)
        .catch(() => setSimilar([]));
    }, 450);
    return () => clearTimeout(timer);
  }, [text]);

  /** Post the question. */
  async function submit() {
    setBusy(true);
    setError("");
    try {
      const t = await confirmPersonalData((confirm) =>
        api<Thread>("/threads", {
          method: "POST",
          body: { group, text, attachments: readyIds(uploads), confirm_personal_data: confirm },
        }),
      );
      if (!t) return setBusy(false);
      router.push(`/t/${t.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not post");
      setBusy(false);
    }
  }

  if (!session) return <div className="card empty"><div className="big">Sign in to ask a question</div><Link href="/signin" className="hint">Sign in →</Link></div>;

  return (
    <div className="card pad stack rise">
      <div>
        <h1 className="page-title">Ask a question</h1>
        <p className="page-sub">Up to 500 characters, formatting and code included. Leaked keys and personal data are blocked automatically.</p>
      </div>
      <div className="field" style={{ maxWidth: 320 }}>
        <label htmlFor="group">Cluster</label>
        <select id="group" className="select" value={group} onChange={(e) => setGroup(e.target.value)}>
          {groups.map((g) => <option key={g.id} value={g.slug}>c/{g.slug}</option>)}
        </select>
      </div>
      <div className="field">
        <label>Your question</label>
        <Editor
          value={text}
          onChange={setText}
          uploads={uploads}
          onUploads={setUploads}
          minHeight={140}
          label="Your question"
          placeholder={"e.g. My k3s pod is in CrashLoopBackOff, how do I find the cause?\n\nUse the toolbar for **bold**, `code` or a code block."}
        />
      </div>
      {text.includes("`") || text.includes("**") || text.includes("\n- ") ? (
        <div className="card pad" style={{ background: "var(--surface-2)" }}>
          <div className="rail-title">Preview</div>
          <RichText text={text} className="post-text" />
        </div>
      ) : null}
      {similar.length > 0 && (
        <div className="card pad rise" style={{ background: "var(--surface-2)" }}>
          <div className="rail-title">These look similar: maybe already answered</div>
          <div className="similar">
            {similar.map((s) => (
              <Link key={s.id} href={`/t/${s.id}`} target="_blank">
                {s.answered && <span style={{ color: "var(--ok)" }}>✓ </span>}c/{s.group} · {s.text.slice(0, 120)}
              </Link>
            ))}
          </div>
        </div>
      )}
      {error && <div className="error">{error}</div>}
      <div className="row">
        <button className="btn primary" disabled={busy || !group || !text.trim() || text.length > LIMIT || stillUploading(uploads)} onClick={submit}>
          {busy ? "Posting…" : stillUploading(uploads) ? "Uploading…" : "Post question"}
        </button>
        <Link href="/" className="btn ghost">Cancel</Link>
      </div>
    </div>
  );
}

/** The ask page. */
export default function SubmitPage() {
  return (
    <Shell rail={<div className="card pad"><div className="rail-title">Before you post</div><div className="hint">Search first: someone may have asked already. Answers written by AI are always approved by a person before they appear.</div></div>}>
      <Suspense fallback={<div className="skeleton" />}><SubmitForm /></Suspense>
    </Shell>
  );
}
