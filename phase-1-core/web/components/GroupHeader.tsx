"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { hueColor } from "@/lib/colors";
import { plural } from "@/lib/format";
import type { Group } from "@/lib/types";
import { useApp } from "./Providers";

/** Join / Leave with an instant (optimistic) change; rolled back if the api refuses. */
export function JoinButton({ group, onChange }: { group: Group; onChange: (g: Group) => void }) {
  const { session, reloadGroups, toast } = useApp();
  const [busy, setBusy] = useState(false);
  if (!session || session.actor !== "human") return null;
  /** Join or leave the cluster. */
  async function toggle() {
    const before = group;
    const joined = !group.joined;
    onChange({ ...group, joined, member_count: group.member_count + (joined ? 1 : -1) });
    setBusy(true);
    try {
      await api(`/groups/${group.slug}/membership`, { method: joined ? "PUT" : "DELETE" });
      void reloadGroups();
    } catch (e) {
      onChange(before);
      toast(e instanceof ApiError ? e.message : "Could not update membership", true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <button className={`btn small ${group.joined ? "ghost joined" : "primary"}`} disabled={busy} onClick={toggle}>
      {group.joined ? <><span className="when-idle">Joined</span><span className="when-hover">Leave</span></> : "Join"}
    </button>
  );
}

/** Group page header: colored banner, name, link part, description, counts, Join. */
export function GroupHeader({ slug }: { slug: string }) {
  const [group, setGroup] = useState<Group | null>(null);
  const [missing, setMissing] = useState(false);
  useEffect(() => {
    api<Group>(`/groups/${slug}`).then(setGroup).catch(() => setMissing(true));
  }, [slug]);
  const color = hueColor(slug);
  return (
    <div className="card group-head">
      <div className="banner" style={{ background: `linear-gradient(120deg, ${color}, color-mix(in srgb, ${color} 45%, var(--surface)))` }} />
      <div className="group-head-body">
        <span className="group-icon" style={{ background: color }}>{slug[0]?.toUpperCase()}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h1 className="page-title">{group?.name ?? (missing ? "Cluster not found" : " ")}</h1>
          <div className="hint mono">c/{slug}</div>
        </div>
        {group && <JoinButton group={group} onChange={setGroup} />}
      </div>
      {group && (
        <div className="group-head-foot">
          {group.description && <p className="page-sub" style={{ margin: 0 }}>{group.description}</p>}
          <div className="hint">{plural(group.member_count, "member")} · {plural(group.thread_count, "question")}</div>
        </div>
      )}
    </div>
  );
}
