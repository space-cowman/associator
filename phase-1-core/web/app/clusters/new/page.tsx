"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Group } from "@/lib/types";
import { useApp } from "@/components/Providers";
import { Shell } from "@/components/Shell";

/** The form to create a public cluster. */
export default function NewCluster() {
  const { session, reloadGroups } = useApp();
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  /** Create the cluster and open it. */
  async function create() {
    setBusy(true);
    setError("");
    try {
      const g = await api<Group>("/groups", { method: "POST", body: { name, description: description.trim() || null } });
      await reloadGroups();
      router.push(`/c/${g.slug}`);
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
            <p className="page-sub">Clusters are communities around a topic.</p>
          </div>
          <div className="field">
            <label htmlFor="name">Name</label>
            <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Kubernetes" maxLength={60} />
            <span className="hint">Its link is made from the name, e.g. #kubernetes</span>
          </div>
          <div className="field">
            <label htmlFor="desc">One-line description (optional)</label>
            <input id="desc" className="input" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Clusters, pods, manifests and the pain in between" maxLength={200} />
          </div>
          {error && <div className="error">{error}</div>}
          <div className="row">
            <button className="btn primary" disabled={busy || name.trim().replace(/[^a-z0-9]/gi, "").length < 2} onClick={create}>{busy ? "Creating…" : "Create group"}</button>
            <Link href="/" className="btn ghost">Cancel</Link>
          </div>
        </div>
      )}
    </Shell>
  );
}
