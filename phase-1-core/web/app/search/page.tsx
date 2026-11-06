"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { SimilarThread } from "@/lib/types";
import { Shell } from "@/components/Shell";
import { RichText } from "@/components/RichText";

/** The search results. */
function Results() {
  const q = useSearchParams().get("q") ?? "";
  const [items, setItems] = useState<SimilarThread[] | null>(null);
  useEffect(() => {
    if (!q.trim()) return setItems([]);
    setItems(null);
    api<SimilarThread[]>("/threads/search-similar", { method: "POST", body: { text: q.slice(0, 500), limit: 10 } })
      .then(setItems)
      .catch(() => setItems([]));
  }, [q]);
  return (
    <>
      <div>
        <h1 className="page-title">Search</h1>
        <p className="page-sub">Questions matching “{q}”</p>
      </div>
      {items === null && <div className="skeleton" />}
      {items?.length === 0 && <div className="card empty"><div className="big">Nothing found</div><Link href="/submit" className="hint">Ask it →</Link></div>}
      {items?.map((s, i) => (
        <Link key={s.id} href={`/t/${s.id}`} className="card post rise" style={{ animationDelay: `${i * 45}ms` }}>
          <div className="meta"><span className="group">c/{s.group}</span>{s.answered && <span className="pill ok">✓ Satisfied</span>}</div>
          <RichText text={s.text} className="post-text" />
        </Link>
      ))}
    </>
  );
}

/** The search page. */
export default function SearchPage() {
  return (
    <Shell>
      <Suspense fallback={<div className="skeleton" />}><Results /></Suspense>
    </Shell>
  );
}
