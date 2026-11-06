"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Draft } from "@/lib/types";
import { DraftCard } from "@/components/DraftCard";
import { useApp } from "@/components/Providers";
import { Shell } from "@/components/Shell";

/** Your AI drafts waiting for approval. */
export default function DraftsPage() {
  const { session, ready } = useApp();
  const [drafts, setDrafts] = useState<Draft[] | null>(null);

  const load = useCallback(() => {
    api<Draft[]>("/drafts?status=pending").then(setDrafts).catch(() => setDrafts([]));
  }, []);
  useEffect(() => { if (session) load(); }, [session, load]);

  return (
    <Shell rail={<div className="card pad"><div className="rail-title">How drafts work</div><div className="hint">Answers written by your AI — on this site or from Claude/ChatGPT via MCP — wait here. Nothing is published until you approve it. You can edit first.</div></div>}>
      <div>
        <h1 className="page-title">Drafts awaiting approval</h1>
        <p className="page-sub">Approve, edit or discard</p>
      </div>
      {ready && !session && <div className="card empty"><div className="big">Sign in to see your drafts</div><Link href="/signin" className="hint">Sign in →</Link></div>}
      {session && drafts === null && <div className="skeleton" />}
      {drafts?.length === 0 && <div className="card empty"><div className="big">Nothing waiting</div>Ask your AI for a draft from any question.</div>}
      {drafts?.map((d) => (
        <DraftCard key={d.id} draft={d} showThread onDone={() => setDrafts((x) => (x ?? []).filter((y) => y.id !== d.id))} />
      ))}
    </Shell>
  );
}
