"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useApp } from "@/components/Providers";
import { api, ApiError } from "@/lib/api";
import { LEGAL } from "@/lib/legal";

const PATTERN = /^[a-z0-9-]{3,30}$/;

/** First sign-in: choose the public @handle (the only thing others ever see about you). */
export default function ChooseHandle() {
  const { signIn } = useApp();
  const router = useRouter();
  const [handle, setHandle] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const valid = PATTERN.test(handle) && !handle.startsWith("-") && !handle.endsWith("-");

  /** Create the account with the chosen handle. */
  async function create() {
    setBusy(true);
    setError("");
    try {
      const { access_token } = await api<{ access_token: string }>("/auth/signup", { method: "POST", body: { handle, accept_terms: true, terms_version: LEGAL.version } });
      await signIn(access_token);
      router.replace("/");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create your account");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card rise" style={{ alignItems: "stretch", textAlign: "left" }}>
        <h1 className="auth-title" style={{ textAlign: "center" }}>Choose your handle</h1>
        <div className="field">
          <label htmlFor="handle">Handle</label>
          <div className="handle-input">
            <span>@</span>
            <input id="handle" className="input" value={handle} autoFocus maxLength={30} autoComplete="off" spellCheck={false}
              onChange={(e) => setHandle(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
              onKeyDown={(e) => e.key === "Enter" && valid && agreed && !busy && void create()} />
          </div>
          <span className="hint">Your public name. 3–30 characters: a–z, 0–9 and dashes.</span>
        </div>
        <label className="consent">
          <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
          <span>
            I am 18 or older and agree to the <Link href="/terms" target="_blank">Terms</Link> and{" "}
            <Link href="/privacy" target="_blank">Privacy Policy</Link>.
          </span>
        </label>
        {error && <div className="error">{error}</div>}
        <button className="btn primary block" disabled={!valid || !agreed || busy} onClick={create}>
          {busy ? "Creating…" : "Continue"}
        </button>
      </div>
    </div>
  );
}
