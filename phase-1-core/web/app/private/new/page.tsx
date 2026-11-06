"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Conversation } from "@/lib/types";
import { PeoplePicker } from "@/components/PeoplePicker";
import { useApp } from "@/components/Providers";
import { Shell } from "@/components/Shell";

/** Like "New group": pick people → name it → create. */
export default function NewPrivateCluster() {
  const { session, toast } = useApp();
  const router = useRouter();
  const [step, setStep] = useState<"people" | "name">("people");
  const [people, setPeople] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  /** Create the private cluster and open it. */
  async function create() {
    setBusy(true);
    setError("");
    try {
      const r = await api<{ conversation: Conversation; not_invited: string[] }>("/conversations", {
        method: "POST",
        body: { name, members: people },
      });
      if (r.not_invited.length) toast(`Could not invite ${r.not_invited.map((h) => "@" + h).join(", ")}`, true);
      router.push(`/private/${r.conversation.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create the cluster");
      setBusy(false);
    }
  }

  return (
    <Shell>
      {!session ? (
        <div className="card empty"><div className="big">Sign in to create a cluster</div><Link href="/signin" className="hint">Sign in →</Link></div>
      ) : (
        <div className="card pad stack rise">
          <div>
            <h1 className="page-title">New cluster</h1>
            <p className="page-sub">{step === "people" ? "Add people (you can add more later)." : "Give it a name."}</p>
          </div>
          {step === "people" ? (
            <>
              <PeoplePicker picked={people} onChange={setPeople} exclude={session ? [session.handle] : []} />
              <div className="row">
                <button className="btn primary" onClick={() => setStep("name")}>{people.length ? "Next" : "Skip for now"}</button>
                <Link href="/private" className="btn ghost">Cancel</Link>
              </div>
            </>
          ) : (
            <>
              <div className="field">
                <label htmlFor="name">Cluster name</label>
                <input id="name" className="input" autoFocus value={name} maxLength={60} onChange={(e) => setName(e.target.value)} placeholder="Goa trip" />
              </div>
              <div className="notice">
                <strong>Private cluster:</strong> messages here are visible only to its members, not to the public.
                {people.length > 0 && ` ${people.length} ${people.length === 1 ? "person gets" : "people get"} an invitation to accept.`}
              </div>
              {error && <div className="error">{error}</div>}
              <div className="row">
                <button className="btn primary" disabled={busy || !name.trim()} onClick={create}>{busy ? "Creating…" : "Create cluster"}</button>
                <button className="btn ghost" onClick={() => setStep("people")}>Back</button>
              </div>
            </>
          )}
        </div>
      )}
    </Shell>
  );
}
