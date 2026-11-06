"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { AccessToken, MemoryItem, SavedModel } from "@/lib/types";
import { useApp } from "@/components/Providers";
import { Shell } from "@/components/Shell";
import { CopyIcon } from "@/components/Icons";

const PROVIDERS = [
  { id: "openrouter", label: "OpenRouter", hint: "e.g. nvidia/nemotron-3.5-lightning:free (beta: :free models only)" },
  { id: "openai", label: "OpenAI (ChatGPT)", hint: "e.g. gpt-4o-mini" },
  { id: "anthropic", label: "Anthropic (Claude)", hint: "e.g. claude-haiku-5-5" },
  { id: "gemini", label: "Google Gemini", hint: "e.g. gemini-2.5-flash" },
];

const STRENGTHS = [
  { id: "coding", label: "Coding" },
  { id: "reasoning", label: "Reasoning" },
  { id: "writing", label: "Writing" },
  { id: "cheap", label: "Cheap" },
];
const MAX_MODELS = 3;

/** Add or remove a value from a list. */
const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((t) => t !== id) : [...list, id]);

/** Your saved AI models. */
function MyModels() {
  const { toast } = useApp();
  const [models, setModels] = useState<SavedModel[] | null>(null);
  const [provider, setProvider] = useState("openrouter");
  const [model, setModel] = useState("");
  const [label, setLabel] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(() => { api<SavedModel[]>("/me/models").then(setModels).catch(() => setModels([])); }, []);
  useEffect(load, [load]);

  /** Save a new model and its key. */
  async function save() {
    setError("");
    try {
      await api("/me/models", {
        method: "POST",
        body: { provider, model, api_key: key, label: label.trim() || undefined, strengths: tags },
      });
      setKey("");
      setModel("");
      setLabel("");
      setTags([]);
      toast("Model saved — the key is encrypted and never shown again");
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save");
    }
  }
  /** Change a model's settings. */
  async function change(m: SavedModel, body: Partial<Pick<SavedModel, "enabled" | "strengths">>) {
    try {
      await api(`/me/models/${m.id}`, { method: "PATCH", body });
      load();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not save", true);
    }
  }
  /** Delete a model. */
  async function remove(id: string) {
    if (!confirm("Delete this model and its encrypted key?")) return;
    await api(`/me/models/${id}`, { method: "DELETE" }).catch(() => undefined);
    load();
  }

  return (
    <section className="card pad stack">
      <div>
        <h2 className="page-title" style={{ fontSize: 18 }}>My AI models</h2>
        <p className="page-sub">
          Used by “Ask my AI” — up to {MAX_MODELS}. Tags say what each one is good at, so each part of a question goes to the
          right one. Keys are encrypted (AWS KMS) and only ever shown as their last 4 characters.
        </p>
      </div>
      {models === null ? <div className="skeleton" style={{ height: 60 }} /> : models.map((m) => (
        <div key={m.id} className="card pad stack" style={{ background: "var(--surface-2)", gap: 8, opacity: m.enabled ? 1 : 0.6 }}>
          <div className="row spread">
            <div>
              <div style={{ fontWeight: 500 }}>{m.label ?? m.provider} · <span className="mono">{m.model}</span></div>
              <div className="hint mono">{m.label ? `${m.provider} · ` : ""}key ••••{m.key_last4}</div>
            </div>
            <div className="row">
              <label className="row hint" style={{ gap: 6 }}>
                <input type="checkbox" checked={m.enabled} onChange={(e) => change(m, { enabled: e.target.checked })} /> On
              </label>
              <button className="btn small danger" onClick={() => remove(m.id)}>Delete</button>
            </div>
          </div>
          <div className="row" style={{ gap: 6 }} role="group" aria-label={`Strengths of ${m.label ?? m.model}`}>
            {STRENGTHS.map((s) => (
              <button key={s.id} type="button" className={`chip${m.strengths.includes(s.id) ? " on" : ""}`}
                aria-pressed={m.strengths.includes(s.id)} onClick={() => change(m, { strengths: toggle(m.strengths, s.id) })}>
                {s.label}
              </button>
            ))}
          </div>
        </div>
      ))}
      {models !== null && models.length < MAX_MODELS && (
        <div className="stack" style={{ gap: 10 }}>
          {models.length > 0 && <h3 style={{ fontSize: 15, margin: 0 }}>Add a model</h3>}
          <div className="row">
            <div className="field" style={{ flex: 1, minWidth: 180 }}>
              <label htmlFor="prov">Provider</label>
              <select id="prov" className="select" value={provider} onChange={(e) => setProvider(e.target.value)}>
                {PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
              </select>
            </div>
            <div className="field" style={{ flex: 2, minWidth: 220 }}>
              <label htmlFor="model">Model</label>
              <input id="model" className="input mono" value={model} onChange={(e) => setModel(e.target.value)} placeholder={PROVIDERS.find((p) => p.id === provider)?.hint} />
            </div>
          </div>
          <div className="field">
            <label htmlFor="key">API key</label>
            <input id="key" className="input mono" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder="Pasted here, encrypted before it is stored" />
          </div>
          <div className="field">
            <label htmlFor="mlabel">Name (optional)</label>
            <input id="mlabel" className="input" maxLength={40} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Work Claude" />
          </div>
          <div className="field">
            <label id="mtags">Good at (optional)</label>
            <div className="row" style={{ gap: 6 }} role="group" aria-labelledby="mtags">
              {STRENGTHS.map((s) => (
                <button key={s.id} type="button" className={`chip${tags.includes(s.id) ? " on" : ""}`}
                  aria-pressed={tags.includes(s.id)} onClick={() => setTags(toggle(tags, s.id))}>
                  {s.label}
                </button>
              ))}
            </div>
          </div>
          {error && <div className="error">{error}</div>}
          <button className="btn primary small" style={{ alignSelf: "flex-start" }} disabled={!model.trim() || key.length < 20} onClick={save}>Save model</button>
        </div>
      )}
    </section>
  );
}

const MEMORY_CHARS = 4000;

/** Your AI memory. */
function MyMemory() {
  const { toast } = useApp();
  const [items, setItems] = useState<MemoryItem[] | null>(null);
  const [pasted, setPasted] = useState("");
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(() => { api<MemoryItem[]>("/me/memory").then(setItems).catch(() => setItems([])); }, []);
  useEffect(load, [load]);

  /** Run a change and show the result. */
  async function run(work: () => Promise<unknown>, done?: string) {
    setBusy(true);
    setError("");
    try {
      await work();
      if (done) toast(done);
      load();
      return true;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save");
      return false;
    } finally {
      setBusy(false);
    }
  }
  /** Import memory from pasted text. */
  async function importText() {
    if (await run(() => api("/me/memory/import", { method: "POST", body: { text: pasted } }), "Memory saved, encrypted")) setPasted("");
  }
  /** Save an edited memory item. */
  async function saveEdit() {
    if (!editing) return;
    if (await run(() => api(`/me/memory/${editing.id}`, { method: "PATCH", body: { text: editing.text } }))) setEditing(null);
  }
  /** Delete all memory. */
  async function removeAll() {
    if (!confirm("Delete all your memory? This cannot be undone.")) return;
    await run(() => api("/me/memory", { method: "DELETE" }), "Memory deleted");
  }

  return (
    <section className="card pad stack">
      <div>
        <h2 className="page-title" style={{ fontSize: 18 }}>My memory</h2>
        <p className="page-sub">
          What your AI knows about you, so “Ask my AI” can answer like it. Encrypted, used only when you turn on “Use my memory”
          for a draft, and only with your own models. Never shown to anyone else.
        </p>
      </div>
      {items === null ? <div className="skeleton" style={{ height: 60 }} /> : items.map((m) => (
        <div key={m.id} className="row spread card pad" style={{ background: "var(--surface-2)", gap: 8 }}>
          {editing?.id === m.id ? (
            <>
              <input className="input" style={{ flex: 1 }} maxLength={300} value={editing.text} aria-label="Edit memory item"
                onChange={(e) => setEditing({ id: m.id, text: e.target.value })} />
              <div className="row">
                <button className="btn small primary" disabled={busy || !editing.text.trim()} onClick={saveEdit}>Save</button>
                <button className="btn small ghost" onClick={() => setEditing(null)}>Cancel</button>
              </div>
            </>
          ) : (
            <>
              <div style={{ flex: 1 }}>
                <div>{m.text}</div>
                {!m.searchable && <div className="hint">found by keywords only</div>}
              </div>
              <div className="row">
                <button className="btn small ghost" aria-label={`Edit: ${m.text}`} onClick={() => setEditing({ id: m.id, text: m.text })}>Edit</button>
                <button className="btn small danger" aria-label={`Delete: ${m.text}`}
                  onClick={() => run(() => api(`/me/memory/${m.id}`, { method: "DELETE" }))}>Delete</button>
              </div>
            </>
          )}
        </div>
      ))}
      <div className="field">
        <label htmlFor="memory-import">{items && items.length > 0 ? "Add more" : "Import"}</label>
        <textarea id="memory-import" className="textarea" rows={5} maxLength={MEMORY_CHARS} value={pasted}
          onChange={(e) => setPasted(e.target.value)}
          placeholder="Ask your own AI: “What do you know about me? List it, one fact per line.” Paste the answer here." />
        <div className="hint">{pasted.length}/{MEMORY_CHARS} · one item per line · keys and passwords are refused</div>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="row spread">
        <button className="btn primary small" disabled={busy || !pasted.trim()} onClick={importText}>{busy ? "Saving…" : "Save to memory"}</button>
        {items && items.length > 0 && <button className="btn small danger" disabled={busy} onClick={removeAll}>Delete all memory</button>}
      </div>
    </section>
  );
}

/** Access tokens for your AI apps. */
function Tokens() {
  const { toast } = useApp();
  const [tokens, setTokens] = useState<AccessToken[]>([]);
  const [fresh, setFresh] = useState("");
  const load = useCallback(() => { api<AccessToken[]>("/me/tokens").then(setTokens).catch(() => setTokens([])); }, []);
  useEffect(load, [load]);

  /** Create a token and show it once. */
  async function create() {
    try {
      const t = await api<AccessToken & { token: string }>("/me/tokens", { method: "POST", body: { name: "claude-code" } });
      setFresh(t.token);
      load();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not create a token", true);
    }
  }
  /** Revoke a token. */
  async function revoke(id: string) {
    await api(`/me/tokens/${id}`, { method: "DELETE" }).catch(() => undefined);
    toast("Token revoked");
    load();
  }
  const active = tokens.filter((t) => !t.revoked_at && new Date(t.expires_at) > new Date());

  return (
    <section className="card pad stack">
      <div>
        <h2 className="page-title" style={{ fontSize: 18 }}>AI app access (MCP)</h2>
        <p className="page-sub">Lets Claude Code or another AI app use Associator as you. Questions it posts are labelled “Asked by Agent”; its answers wait in your drafts.</p>
      </div>
      {fresh && (
        <div className="stack" style={{ gap: 6 }}>
          <div className="hint">Copy it now — it is shown only once:</div>
          <div className="secret">{fresh}</div>
          <button className="btn small" style={{ alignSelf: "flex-start" }} onClick={() => { void navigator.clipboard.writeText(fresh); toast("Copied"); }}><CopyIcon /> Copy</button>
        </div>
      )}
      {active.map((t) => (
        <div key={t.id} className="row spread">
          <div>
            <div style={{ fontWeight: 500 }}>{t.name} <span className="hint mono">••••{t.token_last4}</span></div>
            <div className="hint">{t.last_used_at ? `last used ${new Date(t.last_used_at).toLocaleString()}` : "never used"} · expires {new Date(t.expires_at).toLocaleDateString()}</div>
          </div>
          <button className="btn small danger" onClick={() => revoke(t.id)}>Revoke</button>
        </div>
      ))}
      <button className="btn small" style={{ alignSelf: "flex-start" }} onClick={create}>Create access token</button>
    </section>
  );
}

/** People you blocked. */
function Blocked() {
  const { toast } = useApp();
  const [handles, setHandles] = useState<string[] | null>(null);
  const load = useCallback(() => { api<string[]>("/me/blocks").then(setHandles).catch(() => setHandles([])); }, []);
  useEffect(load, [load]);

  /** Unblock a person. */
  async function unblock(h: string) {
    await api(`/me/blocks/${h}`, { method: "DELETE" }).catch(() => undefined);
    toast(`Unblocked @${h}`);
    load();
  }

  return (
    <section className="card pad stack">
      <div>
        <h2 className="page-title" style={{ fontSize: 18 }}>Blocked people</h2>
        <p className="page-sub">They can't invite you to clusters or message you. They are not told.</p>
      </div>
      {handles === null ? <div className="skeleton" style={{ height: 40 }} /> : handles.length === 0 ? (
        <span className="hint">No one blocked</span>
      ) : (
        handles.map((h) => (
          <div key={h} className="row spread">
            <span>@{h}</span>
            <button className="btn small" onClick={() => unblock(h)}>Unblock</button>
          </div>
        ))
      )}
    </section>
  );
}

/** The settings page. */
export default function SettingsPage() {
  const { session, ready } = useApp();
  return (
    <Shell>
      <div><h1 className="page-title">Settings</h1></div>
      {ready && !session && <div className="card empty"><div className="big">Sign in to see your settings</div><Link href="/signin" className="hint">Sign in →</Link></div>}
      {session && <><MyModels /><MyMemory /><Tokens /><Blocked /></>}
    </Shell>
  );
}
