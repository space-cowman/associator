"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ConversationDetail } from "@/lib/types";
import { Avatar } from "./Avatar";
import { CloseIcon, MoreIcon, PlusIcon } from "./Icons";
import { Menu } from "./Menu";
import { PeoplePicker } from "./PeoplePicker";
import { useApp } from "./Providers";

type Run = (fn: () => Promise<unknown>, done?: string) => Promise<void>;

/** Who is in the chat and (admins) its settings, in a panel that slides in from the right (a sheet from the bottom on phones). */
export function ChatDetails({ c, id, open, onClose, run, onLeave }: {
  c: ConversationDetail; id: string; open: boolean; onClose: () => void; run: Run; onLeave: () => void;
}) {
  const { session, toast } = useApp();
  const cluster = c.kind === "cluster";
  const admin = cluster && c.my_role === "admin" && c.my_state === "active";
  const me = session?.handle;
  const active = c.members.filter((m) => m.state === "active");
  const invited = c.members.filter((m) => m.state === "invited");
  const [inviting, setInviting] = useState(false);
  const [adding, setAdding] = useState<string[]>([]);
  const [name, setName] = useState(c.title);
  useEffect(() => setName(c.title), [c.title]);
  useEffect(() => {
    if (!open) return;
    /** Close on Escape. */
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [open, onClose]);

  /** Save the new name. */
  function rename() {
    const next = name.trim();
    if (!next || next === c.title) return setName(c.title);
    void run(() => api(`/conversations/${id}`, { method: "PATCH", body: { name: next } }), "Renamed");
  }

  /** Send the invitations. */
  function invite() {
    void run(async () => {
      const r = await api<{ not_invited: string[] }>(`/conversations/${id}/members`, { method: "POST", body: { handles: adding } });
      setAdding([]);
      setInviting(false);
      if (r.not_invited.length) toast(`Could not invite ${r.not_invited.map((h) => "@" + h).join(", ")}`, true);
    }, "Invitations sent");
  }

  return (
    <div className={`sheet-wrap${open ? " open" : ""}`} inert={!open}>
      <div className="sheet-backdrop" onClick={onClose} />
      <aside className="sheet" role="dialog" aria-modal="true" aria-label="Details">
        <div className="sheet-grip" aria-hidden="true" />
        <div className="sheet-head">
          <span>Details</span>
          <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}><CloseIcon /></button>
        </div>
        <div className="sheet-hero">
          <Avatar handle={cluster ? c.title : c.title.slice(1)} size={64} />
          {admin ? (
            <input className="title-edit" aria-label="Cluster name" value={name} maxLength={60}
              onChange={(e) => setName(e.target.value)} onBlur={rename}
              onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }} />
          ) : (
            <div className="sheet-title">{c.title}</div>
          )}
          <div className="hint">{cluster ? "Private cluster · visible only to its members" : "Private chat"}</div>
        </div>

        <section className="sheet-group">
          <div className="sheet-label">{cluster ? `Members · ${active.length}` : "People"}</div>
          {active.map((m) => (
            <div key={m.handle} className="sheet-row">
              <Avatar handle={m.handle} size={30} />
              <span className="grow">@{m.handle}{m.handle === me ? " (you)" : ""}</span>
              {cluster && m.role === "admin" && <span className="pill">admin</span>}
              {admin && m.handle !== me && (
                <Menu label={`Manage @${m.handle}`} icon={<MoreIcon size={17} />} items={[
                  { label: m.role === "admin" ? "Remove admin" : "Make admin", onSelect: () => void run(() => api(`/conversations/${id}/members/${m.handle}/role`, { method: "PUT", body: { role: m.role === "admin" ? "member" : "admin" } })) },
                  { label: "Remove from cluster", danger: true, onSelect: () => { if (confirm(`Remove @${m.handle}?`)) void run(() => api(`/conversations/${id}/members/${m.handle}`, { method: "DELETE" })); } },
                ]} />
              )}
            </div>
          ))}
          {invited.map((m) => (
            <div key={m.handle} className="sheet-row">
              <Avatar handle={m.handle} size={30} />
              <span className="grow hint">@{m.handle} · {cluster ? "invited" : "waiting to accept"}</span>
              {admin && (
                <button type="button" className="btn small ghost" onClick={() => void run(() => api(`/conversations/${id}/members/${m.handle}`, { method: "DELETE" }), "Invitation cancelled")}>
                  Cancel
                </button>
              )}
            </div>
          ))}
          {admin && (inviting ? (
            <div className="stack sheet-invite">
              <PeoplePicker picked={adding} onChange={setAdding} exclude={c.members.map((m) => m.handle)} max={50 - c.members.length} />
              <div className="row">
                <button type="button" className="btn small primary" disabled={!adding.length} onClick={invite}>
                  Send {adding.length > 1 ? `${adding.length} invitations` : "invitation"}
                </button>
                <button type="button" className="btn small ghost" onClick={() => { setInviting(false); setAdding([]); }}>Cancel</button>
              </div>
            </div>
          ) : (
            <button type="button" className="sheet-row sheet-action" onClick={() => setInviting(true)}>
              <span className="plus-dot"><PlusIcon size={15} /></span> Invite people
            </button>
          ))}
        </section>

        {admin && (
          <section className="sheet-group">
            <Toggle label="AI in this cluster" hint="Members can ask @platform-ai or their own model with messages they pick."
              checked={c.ai_enabled} onChange={(v) => void run(() => api(`/conversations/${id}`, { method: "PATCH", body: { ai_enabled: v } }))} />
            <Toggle label="Help improve Associator's AI"
              hint="Shares the AI question and answer with names and personal details hidden. Members' messages are never shared. Everyone here sees it is on."
              checked={c.ai_sharing} disabled={!c.ai_enabled}
              onChange={(v) => void run(() => api(`/conversations/${id}`, { method: "PATCH", body: { ai_sharing: v } }))} />
          </section>
        )}

        <section className="sheet-group">
          <button type="button" className="sheet-row sheet-action danger" onClick={onLeave}>{cluster ? "Leave cluster" : "Leave chat"}</button>
        </section>
      </aside>
    </div>
  );
}

/** An iOS-style switch row. */
function Toggle({ label, hint, checked, disabled = false, onChange }: { label: string; hint: string; checked: boolean; disabled?: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className={`toggle-row${disabled ? " off" : ""}`}>
      <span className="grow">{label}<span className="hint">{hint}</span></span>
      <input type="checkbox" role="switch" className="switch" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}
