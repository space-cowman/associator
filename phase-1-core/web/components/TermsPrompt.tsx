"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { LEGAL } from "@/lib/legal";
import { useApp } from "./Providers";

/** After the Terms or Privacy Policy change, people who accepted an older version are asked once to accept the new one (consent is recorded per version). */
export function TermsPrompt() {
  const { session, signOut, toast } = useApp();
  const [needed, setNeeded] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!session || session.actor !== "human") return setNeeded(false);
    api<{ terms_current: boolean }>("/me").then((m) => setNeeded(!m.terms_current)).catch(() => setNeeded(false));
  }, [session]);

  /** Accept the current Terms. */
  async function accept() {
    setBusy(true);
    try {
      await api("/me/terms", { method: "POST", body: { version: LEGAL.version } });
      setNeeded(false);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not save, try again", true);
    } finally {
      setBusy(false);
    }
  }

  if (!needed) return null;
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="terms-title">
      <div className="card pad stack modal">
        <h2 id="terms-title" className="page-title" style={{ fontSize: 18 }}>We updated our Terms and Privacy Policy</h2>
        <p className="page-sub">
          Version {LEGAL.version} changes what we tell you about private chats and AI quality: cluster admins can now choose to share
          AI questions and answers, with personal details hidden, to help improve Associator&apos;s AI.
        </p>
        <p className="hint">
          Read the <Link href="/terms" target="_blank">Terms</Link> and the <Link href="/privacy" target="_blank">Privacy Policy</Link>.
          To keep using {LEGAL.service}, please accept them.
        </p>
        <div className="row">
          <button className="btn primary" disabled={busy} onClick={accept}>{busy ? "Saving…" : "I accept"}</button>
          <button className="btn ghost" onClick={signOut}>Sign out</button>
        </div>
      </div>
    </div>
  );
}
