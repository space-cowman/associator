"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApp } from "./Providers";

const REASONS: [string, string][] = [
  ["spam", "Spam or scam"],
  ["harassment", "Harassment or bullying"],
  ["hate", "Hate speech"],
  ["sexual", "Sexual content"],
  ["violence", "Violence or threats"],
  ["self_harm", "Self-harm"],
  ["illegal", "Illegal content"],
  ["other", "Something else"],
];

/** "⚑ Report" on a public question or reply. */
export function ReportButton({ path, label = "this post" }: { path: string; label?: string }) {
  const { session, toast } = useApp();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("spam");
  const [details, setDetails] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  if (!session || session.actor !== "human") return null;

  /** Send the report. */
  async function send() {
    setBusy(true);
    try {
      await api(`${path}/report`, { method: "POST", body: { reason, details } });
      toast("Report sent. Thank you — our team will review it.");
      setDone(true);
      setOpen(false);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not send the report", true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className="act" onClick={() => setOpen(true)} disabled={done} title={done ? "You reported this" : `Report ${label}`}>
        ⚑ {done ? "Reported" : "Report"}
      </button>
      {open && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="report-title" onClick={() => setOpen(false)}>
          <div className="card pad stack modal" onClick={(e) => e.stopPropagation()}>
            <h2 id="report-title" className="page-title" style={{ fontSize: 18 }}>Report {label}</h2>
            <p className="hint">Our moderators review every report. The person you report is not told who reported them.</p>
            <div className="field">
              <label htmlFor="report-reason">Reason</label>
              <select id="report-reason" className="select" value={reason} onChange={(e) => setReason(e.target.value)}>
                {REASONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="report-details">Details (optional)</label>
              <textarea id="report-details" className="textarea" rows={3} maxLength={1000} value={details} onChange={(e) => setDetails(e.target.value)} />
            </div>
            <div className="row">
              <button className="btn primary" disabled={busy} onClick={send}>{busy ? "Sending…" : "Send report"}</button>
              <button className="btn ghost" onClick={() => setOpen(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
