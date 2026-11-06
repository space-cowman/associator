"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { Avatar } from "@/components/Avatar";
import { Feed } from "@/components/Feed";
import { CheckIcon } from "@/components/Icons";
import { Shell } from "@/components/Shell";
import { api } from "@/lib/api";
import { hueColor } from "@/lib/colors";
import { score, timeAgo } from "@/lib/format";
import type { Profile, ProfileAnswer } from "@/lib/types";

const PAGE = 20;

/** A person's answers. */
function Answers({ handle }: { handle: string }) {
  const [items, setItems] = useState<ProfileAnswer[] | null>(null);
  const [more, setMore] = useState(false);
  const load = useCallback(async (offset: number) => {
    const page = await api<ProfileAnswer[]>(`/users/${handle}/answers?limit=${PAGE}&offset=${offset}`).catch(() => []);
    setItems((old) => (offset === 0 ? page : [...(old ?? []), ...page]));
    setMore(page.length === PAGE);
  }, [handle]);
  useEffect(() => void load(0), [load]);
  if (items === null) return <div className="skeleton" />;
  if (items.length === 0) return <div className="card empty"><div className="big">No answers yet</div></div>;
  return (
    <div className="stack">
      {items.map((a) => (
        <Link key={a.id} href={`/t/${a.thread_id}#r-${a.id}`} className="card pad answer-item rise">
          <div className="hint">c/{a.group} · {timeAgo(a.created_at)}{a.via === "agent" ? " · Answered by Agent" : a.via === "assisted" ? " · Assisted by Agent" : ""}</div>
          <div className="answer-q">“{a.thread_text.slice(0, 120)}{a.thread_text.length > 120 ? "…" : ""}”</div>
          <div className="answer-text">{a.text.slice(0, 220)}{a.text.length > 220 ? "…" : ""}</div>
          <div className="row hint">
            <span>▲ {score(a.votes.human)}</span>
            {a.satisfied && <span className="pill ok"><CheckIcon size={12} /> Satisfied</span>}
          </div>
        </Link>
      ))}
      {more && <button className="btn ghost" onClick={() => void load(items.length)}>Load more</button>}
    </div>
  );
}

/** A person's public profile. */
export default function ProfilePage() {
  const { handle } = useParams<{ handle: string }>();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [missing, setMissing] = useState(false);
  const [tab, setTab] = useState<"questions" | "answers">("questions");
  useEffect(() => {
    api<Profile>(`/users/${handle}`).then(setProfile).catch(() => setMissing(true));
  }, [handle]);
  const color = hueColor(handle);
  const stats: [string, number | undefined][] = [
    ["Reputation", profile?.reputation],
    ["Questions", profile?.questions],
    ["Answers", profile?.answers],
    ["Satisfied", profile?.satisfied],
  ];
  return (
    <Shell>
      <div className="card profile-head">
        <div className="banner" style={{ background: `linear-gradient(120deg, ${color}, color-mix(in srgb, ${color} 40%, var(--surface)))` }} />
        <div className="profile-body">
          <div className="profile-avatar"><Avatar handle={handle} size={72} /></div>
          <h1 className="page-title">@{handle}</h1>
          <div className="hint">{missing ? "No one has this handle" : profile ? `Joined ${timeAgo(profile.joined_at)}` : " "}</div>
          <div className="stats">
            {stats.map(([label, n]) => (
              <div key={label} className="stat"><b>{n ?? "–"}</b><span>{label}</span></div>
            ))}
          </div>
        </div>
      </div>
      {!missing && (
        <>
          <div className="tabs profile-tabs" role="tablist">
            {(["questions", "answers"] as const).map((t) => (
              <button key={t} role="tab" aria-selected={tab === t} className={`tab${tab === t ? " on" : ""}`} onClick={() => setTab(t)}>
                {t === "questions" ? "Questions" : "Answers"}
              </button>
            ))}
          </div>
          {tab === "questions" ? (
            <Suspense fallback={<div className="skeleton" />}>
              <Feed path={`/users/${handle}/threads`} empty={<div className="big">No questions yet</div>} />
            </Suspense>
          ) : (
            <Answers handle={handle} />
          )}
        </>
      )}
    </Shell>
  );
}
