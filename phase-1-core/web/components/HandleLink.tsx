"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Profile } from "@/lib/types";
import { Avatar } from "./Avatar";

const cache = new Map<string, Promise<Profile | null>>();

/** Load a profile once. */
function loadProfile(handle: string): Promise<Profile | null> {
  if (!cache.has(handle)) cache.set(handle, api<Profile>(`/users/${handle}`).catch(() => null));
  return cache.get(handle)!;
}

/** @handle → profile, with a small profile card on hover (like X / Reddit). */
export function HandleLink({ handle }: { handle: string | null }) {
  const [card, setCard] = useState<Profile | null>(null);
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  if (!handle) return <span className="who">[deleted]</span>;

  /** Show the profile card. */
  const enter = () => {
    timer.current = setTimeout(async () => {
      setCard(await loadProfile(handle));
      setOpen(true);
    }, 380);
  };
  /** Hide the profile card. */
  const leave = () => {
    if (timer.current) clearTimeout(timer.current);
    setOpen(false);
  };

  return (
    <span className="handle-wrap" onMouseEnter={enter} onMouseLeave={leave}>
      <Link href={`/u/${handle}`} className="who" onClick={(e) => e.stopPropagation()}>@{handle}</Link>
      {open && card && (
        <span className="hovercard" onClick={(e) => e.stopPropagation()}>
          <span className="row" style={{ gap: 10 }}>
            <Avatar handle={card.handle} size={40} />
            <span>
              <b>@{card.handle}</b>
              <span className="hint" style={{ display: "block" }}>joined {new Date(card.joined_at).toLocaleDateString()}</span>
            </span>
          </span>
          <span className="hc-stats">
            <span><b>{card.reputation}</b> reputation</span>
            <span><b>{card.answers}</b> answers</span>
            <span><b>{card.satisfied}</b> ✓</span>
          </span>
        </span>
      )}
    </span>
  );
}
