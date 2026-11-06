"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Sort, Thread, Window } from "@/lib/types";
import { PostCard } from "./PostCard";

const PAGE = 15;
const SORTS: { id: Sort; label: string }[] = [
  { id: "hot", label: "Hot" },
  { id: "new", label: "New" },
  { id: "top", label: "Top" },
];
const WINDOWS: { id: Window; label: string }[] = [
  { id: "day", label: "Today" },
  { id: "week", label: "This week" },
  { id: "month", label: "This month" },
  { id: "all", label: "All time" },
];

/** Sorted feed with infinite scroll, a "new posts" pill and keyboard shortcuts (j/k/a/z). */
export function Feed({ path, empty }: { path: string; empty: React.ReactNode }) {
  const params = useSearchParams();
  const router = useRouter();
  const sort = (params.get("sort") as Sort) || "hot";
  const window_ = (params.get("t") as Window) || "week";
  const [items, setItems] = useState<Thread[] | null>(null);
  const [more, setMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [fresh, setFresh] = useState(false);
  const [focus, setFocus] = useState(-1);
  const sentinel = useRef<HTMLDivElement>(null);

  const query = useCallback(
    (extra: string) => `${path}?sort=${sort}${sort === "top" ? `&window=${window_}` : ""}&limit=${PAGE}${extra}`,
    [path, sort, window_],
  );

  const load = useCallback(
    async (reset: boolean, current: Thread[]) => {
      setLoading(true);
      try {
        const last = current[current.length - 1];
        const extra = reset ? "" : sort === "new" ? `&before=${last?.id}` : `&offset=${current.length}`;
        const page = await api<Thread[]>(query(extra));
        setItems(reset ? page : [...current, ...page.filter((p) => !current.some((c) => c.id === p.id))]);
        setMore(page.length === PAGE);
        setError("");
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Could not load questions — is the api tunnel open?");
        setItems((old) => old ?? []);
        setMore(false);
      } finally {
        setLoading(false);
      }
    },
    [query, sort],
  );

  useEffect(() => {
    setItems(null);
    setMore(true);
    setFresh(false);
    setFocus(-1);
    void load(true, []);
  }, [load]);

  useEffect(() => {
    const el = sentinel.current;
    if (!el || !items || !more) return;
    const io = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && !loading) void load(false, items);
    }, { rootMargin: "400px" });
    io.observe(el);
    return () => io.disconnect();
  }, [items, more, loading, load]);

  useEffect(() => {
    if (!items?.length) return;
    const newest = [...items].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
    const timer = setInterval(async () => {
      try {
        const top = await api<Thread[]>(`${path}?sort=new&limit=1`);
        if (top[0] && top[0].created_at > newest.created_at) setFresh(true);
      } catch {
      }
    }, 45_000);
    return () => clearInterval(timer);
  }, [items, path]);

  useEffect(() => {
    /** Keyboard shortcuts for the feed. */
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select, [contenteditable]") || e.metaKey || e.ctrlKey || e.altKey) return;
      const cards = Array.from(document.querySelectorAll<HTMLElement>(".feed .post"));
      if (!cards.length) return;
      if (e.key === "j" || e.key === "k") {
        const next = Math.max(0, Math.min(cards.length - 1, focus + (e.key === "j" ? 1 : -1)));
        setFocus(next);
        cards[next].focus();
        cards[next].scrollIntoView({ block: "center", behavior: "smooth" });
      } else if ((e.key === "a" || e.key === "z") && focus >= 0) {
        cards[focus]?.querySelector<HTMLButtonElement>(`button[aria-label="${e.key === "a" ? "Upvote" : "Downvote"}"]`)?.click();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focus]);

  /** Change the feed order. */
  const setSort = (s: Sort, w?: Window) => {
    const q = new URLSearchParams(params.toString());
    q.set("sort", s);
    if (s === "top") q.set("t", w ?? window_);
    else q.delete("t");
    router.replace(`?${q.toString()}`, { scroll: false });
  };

  return (
    <div className="feed">
      <div className="sortbar card">
        <div className="tabs" role="tablist">
          {SORTS.map((s) => (
            <button key={s.id} role="tab" aria-selected={sort === s.id} className={`tab${sort === s.id ? " on" : ""}`} onClick={() => setSort(s.id)}>
              {s.label}
            </button>
          ))}
        </div>
        {sort === "top" && (
          <select className="select small-select" value={window_} onChange={(e) => setSort("top", e.target.value as Window)} aria-label="Time window">
            {WINDOWS.map((w) => <option key={w.id} value={w.id}>{w.label}</option>)}
          </select>
        )}
        <span className="hint kbd-hint" title="Keyboard shortcuts">j/k move · a/z vote</span>
      </div>
      {fresh && (
        <button className="fresh-pill" onClick={() => { window.scrollTo({ top: 0, behavior: "smooth" }); setSort("new"); setFresh(false); void load(true, []); }}>
          ↑ New posts
        </button>
      )}
      {items === null && [0, 1, 2].map((i) => <div key={i} className="skeleton" />)}
      {error && <div className="card pad error">{error}</div>}
      {items && items.length === 0 && !error && <div className="card empty">{empty}</div>}
      {items?.map((t, i) => <PostCard key={t.id} thread={t} index={i} />)}
      <div ref={sentinel} />
      {loading && items && items.length > 0 && <div className="skeleton" style={{ height: 80 }} />}
      {items && items.length > 0 && !more && <div className="end">You&apos;re all caught up ✓</div>}
    </div>
  );
}
