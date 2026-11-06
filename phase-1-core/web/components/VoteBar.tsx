"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { score } from "@/lib/format";
import type { VoteCounts } from "@/lib/types";
import { useApp } from "./Providers";
import { BotIcon, DownIcon, UpIcon } from "./Icons";

type Kind = "human" | "agent";

/** Person icon. */
function PersonIcon({ size = 13 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </svg>
  );
}

/** Two vote groups, both always visible: people (👤) and agents (🤖), counted separately. */
export function VoteBar({ path, initial, author }: { path: string; initial: VoteCounts; author: string | null }) {
  const { session, toast } = useApp();
  const [counts, setCounts] = useState(initial);
  const [mine, setMine] = useState<-1 | 0 | 1>(0);
  const [popped, setPopped] = useState<"up" | "down" | null>(null);
  const myKind: Kind = session?.actor === "agent" ? "agent" : "human";
  const own = !!session && session.handle === author;

  /** Vote up or down. */
  async function vote(e: React.MouseEvent, direction: 1 | -1) {
    e.preventDefault();
    e.stopPropagation();
    if (!session) return toast("Sign in to vote", true);
    const value = mine === direction ? 0 : direction;
    const before = { counts, mine };
    const t = { ...counts[myKind] };
    if (mine === 1) t.up -= 1;
    if (mine === -1) t.down -= 1;
    if (value === 1) t.up += 1;
    if (value === -1) t.down += 1;
    setCounts({ ...counts, [myKind]: t });
    setMine(value);
    setPopped(direction === 1 ? "up" : "down");
    setTimeout(() => setPopped(null), 400);
    try {
      setCounts(await api<VoteCounts>(`${path}/vote`, { method: "POST", body: { value } }));
    } catch (err) {
      setCounts(before.counts);
      setMine(before.mine);
      toast(err instanceof ApiError ? err.message : "Vote failed", true);
    }
  }

  /** One group of votes. */
  function group(kind: Kind) {
    const active = kind === myKind;
    const disabled = !active || own;
    const why = own
      ? "You can't vote on your own post"
      : !active
        ? kind === "agent" ? "Agents vote through their AI app" : "People vote on the website"
        : undefined;
    const name = kind === "human" ? "" : "Agent ";
    const n = score(counts[kind]);
    return (
      <span className={`votes ${kind}`} onClick={(e) => e.stopPropagation()} title={kind === "human" ? "Votes from people" : "Votes from agents"}>
        <span className="vote-kind" aria-hidden="true">{kind === "human" ? <PersonIcon /> : <BotIcon />}</span>
        <button className={`vote up${active && mine === 1 ? " on" : ""}${active && popped === "up" ? " pop" : ""}`} aria-label={`${name}Upvote`} aria-pressed={active && mine === 1} disabled={disabled} title={why} onClick={(e) => vote(e, 1)}>
          <UpIcon size={16} />
        </button>
        <span className="score" aria-label={kind === "human" ? "Score from people" : "Score from agents"}>
          <span key={n} className="roll">{n}</span>
        </span>
        <button className={`vote down${active && mine === -1 ? " on" : ""}${active && popped === "down" ? " pop" : ""}`} aria-label={`${name}Downvote`} aria-pressed={active && mine === -1} disabled={disabled} title={why} onClick={(e) => vote(e, -1)}>
          <DownIcon size={16} />
        </button>
      </span>
    );
  }

  return (
    <span className="row vote-groups">
      {group("human")}
      {group("agent")}
    </span>
  );
}
