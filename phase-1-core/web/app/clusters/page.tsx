"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { JoinButton } from "@/components/GroupHeader";
import { PlusIcon } from "@/components/Icons";
import { useApp } from "@/components/Providers";
import { Shell } from "@/components/Shell";
import { hueColor } from "@/lib/colors";
import { plural } from "@/lib/format";
import type { Group } from "@/lib/types";

/** Browse and join clusters. */
export default function ExploreClusters() {
  const { groups } = useApp();
  const [list, setList] = useState<Group[]>(groups);
  useEffect(() => setList(groups), [groups]);
  const sorted = [...list].sort((a, b) => b.member_count - a.member_count || b.thread_count - a.thread_count);
  /** Update one cluster in the list after joining or leaving. */
  const update = (g: Group) => setList((old) => old.map((x) => (x.id === g.id ? g : x)));
  return (
    <Shell>
      <div className="spread">
        <div>
          <h1 className="page-title">Explore clusters</h1>
          <p className="page-sub">Find people who know your topic</p>
        </div>
        <Link href="/clusters/new" className="btn small"><PlusIcon size={14} /> New cluster</Link>
      </div>
      {groups.length === 0 && <div className="card empty"><div className="big">No clusters yet</div></div>}
      <div className="group-grid">
        {sorted.map((g, i) => (
          <div key={g.id} className="card group-tile rise" style={{ animationDelay: `${Math.min(i, 10) * 30}ms` }}>
            <div className="tile-banner" style={{ background: hueColor(g.slug) }} />
            <div className="tile-body">
              <Link href={`/c/${g.slug}`} className="tile-name">
                <span className="group-dot" style={{ background: hueColor(g.slug) }}>{g.slug[0]?.toUpperCase()}</span>
                {g.name}
              </Link>
              <p className="hint tile-desc">{g.description || `c/${g.slug}`}</p>
              <div className="spread">
                <span className="hint">{plural(g.member_count, "member")} · {plural(g.thread_count, "question")}</span>
                <JoinButton group={g} onChange={update} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </Shell>
  );
}
