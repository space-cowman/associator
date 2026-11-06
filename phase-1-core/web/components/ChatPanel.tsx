"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { listen } from "@/lib/live";
import type { Attachment, SavedModel } from "@/lib/types";
import { Avatar } from "./Avatar";
import { BotIcon, CloseIcon, CopyIcon, PaperclipIcon, PlusIcon, SendIcon, SparkIcon } from "./Icons";
import { ALLOWED, uploadAttachment } from "./Editor";
import { Menu } from "./Menu";
import { useApp } from "./Providers";

type Status = "starting" | "ready" | "error";
const MAX_TEXT = 4000;
type ApiMessage = {
  id: number;
  kind: "text" | "ask" | "ai";
  sender: string | null;
  mine: boolean;
  text: string | null;
  file: Attachment | null;
  meta: { model?: string; shared?: number[]; asked_by?: string };
  created_at: string;
};
type MessageRecord = {
  logId: number;
  sender: string;
  text: string;
  at: string;
  mine: boolean;
  file?: Attachment;
  agent?: { model: string; askedBy: string };
  sentTo?: { model: string; shared: number[] };
};
/** Turn an api message into a bubble. */
function toRecord(m: ApiMessage): MessageRecord {
  return {
    logId: m.id,
    sender: m.sender ?? "deleted-user",
    text: m.text ?? "",
    at: m.created_at,
    mine: m.mine,
    file: m.file ?? undefined,
    agent: m.kind === "ai" ? { model: m.meta.model ?? "AI", askedBy: m.meta.asked_by ?? "" } : undefined,
    sentTo: m.kind === "ask" ? { model: m.meta.model ?? "AI", shared: m.meta.shared ?? [] } : undefined,
  };
}
/** A file size in KB or MB. */
const sizeLabel = (n: number) => (n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`);
type Agent = { id: "platform" | "mine"; label: string };
const PLATFORM: Agent = { id: "platform", label: "platform-ai" };

/** The conversation: messages (stored by the server, encrypted at rest), composer, live updates, files, and @-mentions: an agent (Platform AI or your own model) answers from the messages you tick. */
export function ChatPanel({ conversationId, aiEnabled, aiSharing = false, people, reporting, onReporting }: {
  conversationId: string; aiEnabled: boolean; aiSharing?: boolean; people: string[]; reporting: boolean; onReporting: (on: boolean) => void;
}) {
  const { session, toast } = useApp();
  const handle = session?.handle ?? "";
  const [messages, setMessages] = useState<MessageRecord[]>([]);
  const [status, setStatus] = useState<Status>("starting");
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const seen = useRef<Set<number>>(new Set());
  const loaded = useRef(false);
  const sharedWith = useMemo(() => {
    const map = new Map<number, string>();
    for (const m of messages) for (const id of m.sentTo?.shared ?? []) map.set(id, m.sentTo!.model);
    return map;
  }, [messages]);

  const last = useRef(0);
  const refresh = useCallback(async () => {
    try {
      const page = await api<ApiMessage[]>(`/conversations/${conversationId}/messages${last.current ? `?after=${last.current}` : ""}`);
      setStatus("ready");
      if (!page.length) return;
      last.current = page[page.length - 1].id;
      setMessages((all) => {
        const known = new Set(all.map((m) => m.logId));
        return [...all, ...page.filter((m) => !known.has(m.id)).map(toRecord)];
      });
    } catch (e) {
      setStatus((s) => (s === "ready" ? s : "error"));
      console.warn("chat refresh failed", e instanceof Error ? e.message : e);
    }
  }, [conversationId]);
  /** Add new messages to the list. */
  function added(list: ApiMessage[]) {
    setMessages((all) => {
      const known = new Set(all.map((m) => m.logId));
      return [...all, ...list.filter((m) => !known.has(m.id)).map(toRecord)];
    });
    last.current = Math.max(last.current, ...list.map((m) => m.id));
  }

  useEffect(() => {
    last.current = 0;
    setMessages([]);
    void refresh();
    const stop = listen((n) => { if (n.conversation_id === conversationId) void refresh(); });
    const poll = setInterval(() => void refresh(), 30_000);
    return () => { stop(); clearInterval(poll); };
  }, [refresh, conversationId]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end", behavior: loaded.current ? "smooth" : "auto" });
  }, [messages.length]);
  useEffect(() => {
    const t = setTimeout(() => { for (const m of messages) seen.current.add(m.logId); }, 400);
    if (!loaded.current && messages.length > 0) {
      for (const m of messages) seen.current.add(m.logId);
      loaded.current = true;
    }
    return () => clearTimeout(t);
  }, [messages]);
  useEffect(() => {
    const el = input.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [draft]);

  const [attached, setAttached] = useState<File | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  const [myModel, setMyModel] = useState<SavedModel | null>(null);
  useEffect(() => { api<SavedModel[]>("/me/models").then((m) => setMyModel(m.find((x) => x.enabled) ?? null)).catch(() => setMyModel(null)); }, []);
  const agents = useMemo<Agent[]>(
    () => (aiEnabled ? [PLATFORM, ...(myModel ? [{ id: "mine" as const, label: myModel.model }] : [])] : []),
    [aiEnabled, myModel],
  );
  const [agent, setAgent] = useState<Agent | null>(null);
  const [ticked, setTicked] = useState<Set<number>>(new Set());
  const [reason, setReason] = useState("harassment");
  const [details, setDetails] = useState("");
  const ticking = agent !== null || reporting;
  const mention = /(^|\s)@([\w.-]*)$/.exec(draft);
  const query = mention ? mention[2].toLowerCase() : null;
  const options = query === null ? null : {
    agents: agents.filter((a) => a.label.toLowerCase().includes(query)),
    people: people.filter((h) => h !== handle && h.includes(query)).slice(0, 6),
  };

  const flat = options ? [...options.agents.map((a) => ({ agent: a })), ...options.people.map((h) => ({ person: h }))] : [];
  const [hi, setHi] = useState(0);
  useEffect(() => setHi(0), [query]);

  /** Pick an AI or a person from the @ list. */
  function choose(option: { agent?: Agent; person?: string }) {
    const before = draft.slice(0, draft.length - (mention ? mention[2].length + 1 : 0));
    if (option.agent) {
      setAgent(option.agent);
      setDraft(before);
    } else if (option.person) {
      setDraft(`${before}@${option.person} `);
    }
  }

  /** Tick or untick a message. */
  function toggle(logId: number) {
    setTicked((t) => {
      const next = new Set(t);
      if (next.has(logId)) next.delete(logId);
      else if (next.size < 30) next.add(logId);
      return next;
    });
  }

  /** Report the ticked messages. */
  async function sendReport() {
    if (!ticked.size) return toast("Tick the messages to report", true);
    try {
      await api(`/conversations/${conversationId}/reports`, {
        method: "POST",
        body: { reason, details, message_ids: [...ticked] },
      });
      toast("Report sent. Thank you — our team will review it.");
      onReporting(false);
      setTicked(new Set());
      setDetails("");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Could not send the report", true);
    }
  }

  /** Ask the AI and add its answer. */
  async function ask(question: string) {
    if (!agent) return;
    const ids = [...ticked];
    setDraft("");
    setAgent(null);
    setTicked(new Set());
    try {
      const out = await api<{ question: ApiMessage; answer: ApiMessage }>(`/conversations/${conversationId}/ai`, {
        method: "POST",
        body: { model: agent.id, question, message_ids: ids },
      });
      added([out.question, out.answer]);
    } catch (e) {
      setDraft(question);
      toast(e instanceof ApiError || e instanceof Error ? e.message : "The AI could not answer", true);
    }
  }

  const [dragging, setDragging] = useState(false);
  /** Open the file picker for a kind of file. */
  function choosePicker(accept: string) {
    if (status !== "ready" || agent) return toast(agent ? "Files can't be sent to an AI" : "The chat is still loading", true);
    if (picker.current) {
      picker.current.accept = accept;
      picker.current.click();
    }
  }
  /** Put a code block in the message. */
  function insertCode() {
    const el = input.current;
    const at = el?.selectionStart ?? draft.length;
    const before = draft.slice(0, at);
    const lead = before && !before.endsWith("\n") ? "\n" : "";
    setDraft(`${before}${lead}\`\`\`\n\n\`\`\`${draft.slice(at)}`);
    requestAnimationFrame(() => {
      const pos = before.length + lead.length + 4;
      el?.focus();
      el?.setSelectionRange(pos, pos);
    });
  }

  /** Attach a file after checking its type and size. */
  function pick(file: File | undefined) {
    if (!file) return;
    if (status !== "ready" || agent) return toast(agent ? "Files can't be sent to an AI" : "The chat is still loading", true);
    const max = ALLOWED[file.type];
    if (!max) return toast("Photos (PNG, JPEG, WebP, GIF), MP4/WebM videos, PDFs and text files only", true);
    if (file.size > max) return toast(`${file.name}: at most ${Math.round(max / 1024 / 1024)} MB for this type`, true);
    setAttached(file);
  }

  /** Send the message, with its file. */
  async function send() {
    const text = draft.trim();
    if (!text && !attached) return;
    setSending(true);
    try {
      if (reporting) return;
      if (agent) {
        if (!text) throw new Error(`Type what you want @${agent.label} to do`);
        await ask(text);
        return;
      }
      const file = attached ? await uploadAttachment(attached) : null;
      const m = await api<ApiMessage>(`/conversations/${conversationId}/messages`, {
        method: "POST",
        body: { text, attachment_id: file?.id ?? null },
      });
      added([m]);
      setDraft("");
      setAttached(null);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Could not send", true);
    } finally {
      setSending(false);
    }
  }

  const rows = layout(messages);
  const canSend = status === "ready" && !sending && (draft.trim() !== "" || attached !== null);

  return (
    <section
      className={`chat${dragging ? " dragging" : ""}`}
      onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDragging(true); } }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false); }}
      onDrop={(e) => { if (!e.dataTransfer.files.length) return; e.preventDefault(); setDragging(false); pick(e.dataTransfer.files[0]); }}
    >
      {dragging && <div className="drop-hint" aria-hidden="true"><PaperclipIcon size={22} /> Drop to attach · encrypted before upload</div>}
      <div className="chat-log" aria-live="polite">
        {messages.length === 0 && (
          <div className="chat-empty">
            <div className="chat-empty-lock" aria-hidden="true">👋</div>
            <div className="big">{status === "error" ? "Couldn't load this chat" : "No messages yet"}</div>
            <span className="hint">
              {status === "error" ? "Check your connection and reload." : "Say hi, share a photo, or type @ to ask an AI. Only the people here can see this chat."}
            </span>
          </div>
        )}
        {rows.map(({ m, own, day, first, last }) => (
          <Fragment key={m.logId}>
            {day && <div className="chat-day"><span>{day}</span></div>}
            <div className={`bubble-row${own ? " mine" : ""}${first ? " first" : ""}${last ? " last" : ""}${loaded.current && !seen.current.has(m.logId) ? " fresh" : ""}`}>
              {ticking && (m.text || reporting) && (
                <input type="checkbox" className="tick" aria-label={reporting ? "Include this message in the report" : "Share this message with the AI"}
                  checked={ticked.has(m.logId)} onChange={() => toggle(m.logId)} />
              )}
              {!own && (
                <span className="bubble-avatar">
                  {last && (m.agent ? <span className="agent-avatar"><BotIcon size={14} /></span> : <Avatar handle={m.sender} size={26} />)}
                </span>
              )}
              <div className={`bubble${m.agent ? " agent" : ""}`} title={new Date(m.at).toLocaleString()}>
                {first && m.agent && <div className="bubble-from">{m.agent.model} · asked by @{m.agent.askedBy}</div>}
                {first && !m.agent && !own && <div className="bubble-from">@{m.sender}</div>}
                {m.file && <FileView conversationId={conversationId} file={m.file} />}
                {m.text && <MessageText text={m.text} />}
                {m.sentTo && <div className="bubble-note">to {m.sentTo.model}{m.sentTo.shared.length ? ` · ${m.sentTo.shared.length} message${m.sentTo.shared.length === 1 ? "" : "s"} shared` : ""}</div>}
                {sharedWith.get(m.logId) && <div className="bubble-note">↗ shared with {sharedWith.get(m.logId)}</div>}
                {last && <div className="bubble-time">{new Date(m.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</div>}
              </div>
            </div>
          </Fragment>
        ))}
        <div ref={bottom} />
      </div>

      <div className="chat-dock">
        {reporting && (
          <div className="dock-card report-bar">
            <div className="row spread">
              <strong>Report messages</strong>
              <button type="button" className="icon-btn" aria-label="Cancel report" onClick={() => { onReporting(false); setTicked(new Set()); }}><CloseIcon size={16} /></button>
            </div>
            <div className="hint">
              {messages.length === 0
                ? "Nothing to report yet."
                : <>Tick the messages to report. They are sent to our moderation team <strong>decrypted</strong>: the only way anyone outside this chat can see them.</>}
            </div>
            {messages.length > 0 && (
              <div className="row">
                <select className="select" value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Reason">
                  <option value="harassment">Harassment or bullying</option>
                  <option value="hate">Hate speech</option>
                  <option value="sexual">Sexual content</option>
                  <option value="violence">Violence or threats</option>
                  <option value="self_harm">Self-harm</option>
                  <option value="illegal">Illegal content</option>
                  <option value="spam">Spam or scam</option>
                  <option value="other">Something else</option>
                </select>
                <input className="input" style={{ flex: 1, minWidth: 140 }} maxLength={1000} value={details} onChange={(e) => setDetails(e.target.value)} placeholder="Details (optional)" />
                <button type="button" className="btn small danger" disabled={!ticked.size} onClick={sendReport}>Report ({ticked.size})</button>
              </div>
            )}
          </div>
        )}
        {options && (options.agents.length > 0 || options.people.length > 0) && (
          <div className="dock-card mention-list" role="listbox">
            {options.agents.length > 0 && <div className="section-label mention-head">Agents</div>}
            {options.agents.map((a, i) => (
              <button type="button" key={a.id} role="option" aria-selected={i === hi} className={`picker-item${i === hi ? " hi" : ""}`} onMouseEnter={() => setHi(i)} onClick={() => choose({ agent: a })}>
                <span className="agent-avatar"><BotIcon size={14} /></span>@{a.label}
              </button>
            ))}
            {options.people.length > 0 && <div className="section-label mention-head">People</div>}
            {options.people.map((h, j) => (
              <button type="button" key={h} role="option" aria-selected={options.agents.length + j === hi} className={`picker-item${options.agents.length + j === hi ? " hi" : ""}`}
                onMouseEnter={() => setHi(options.agents.length + j)} onClick={() => choose({ person: h })}>
                <Avatar handle={h} />@{h}
              </button>
            ))}
          </div>
        )}
        {(attached || agent) && (
          <div className="dock-chips">
            {attached && (
              <span className="person-chip">
                <PaperclipIcon size={14} /> {attached.name} <span className="hint">{sizeLabel(attached.size)}</span>
                <button type="button" aria-label="Remove the file" onClick={() => setAttached(null)} disabled={sending}>×</button>
              </span>
            )}
            {agent && (
              <>
                <span className="person-chip agent-chip">
                  <BotIcon size={13} /> @{agent.label}
                  <button type="button" aria-label="Cancel" onClick={() => { setAgent(null); setTicked(new Set()); }}>×</button>
                </span>
                <span className="hint">
                  {ticked.size ? `${ticked.size} message${ticked.size === 1 ? "" : "s"} shared` : "Tick messages to share"} · names and personal data are masked
                  {aiSharing && " · 🔬 this cluster shares AI questions and answers (masked)"}
                </span>
              </>
            )}
          </div>
        )}
        <div className="msg-composer">
          <input ref={picker} type="file" hidden onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
          <Menu label="Add" icon={<PlusIcon size={18} />} align="start" up className="icon-btn composer-plus" items={[
            { label: "Photo or video", icon: <span className="menu-ico">🖼️</span>, onSelect: () => choosePicker("image/*,video/*") },
            { label: "File", icon: <PaperclipIcon size={16} />, onSelect: () => choosePicker("") },
            { label: "Code block", icon: <span className="menu-ico mono">{"</>"}</span>, onSelect: insertCode },
            ...(agents.length ? [{ label: "Ask AI", icon: <SparkIcon size={16} />, onSelect: () => { setDraft((d) => (d && !d.endsWith(" ") ? d + " @" : d + "@")); input.current?.focus(); } }] : []),
          ]} />
          <textarea
            ref={input}
            className="composer-input"
            rows={1}
            value={draft}
            maxLength={MAX_TEXT}
            disabled={status !== "ready" || sending}
            placeholder={status === "ready" ? (agent ? `Ask @${agent.label}…` : aiEnabled ? "Message · @ to ask AI" : "Message") : status === "error" ? "Couldn't load this chat: reload to retry" : "Loading…"}
            onChange={(e) => setDraft(e.target.value)}
            onPaste={(e) => { const file = e.clipboardData.files[0]; if (file) { e.preventDefault(); pick(file); } }}
            onKeyDown={(e) => {
              if (flat.length) {
                if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                  e.preventDefault();
                  setHi((i) => (i + (e.key === "ArrowDown" ? 1 : flat.length - 1)) % flat.length);
                  return;
                }
                if ((e.key === "Enter" && !e.shiftKey) || e.key === "Tab") {
                  e.preventDefault();
                  choose(flat[Math.min(hi, flat.length - 1)]);
                  return;
                }
              }
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); }
            }}
            aria-label="Message"
          />
          <button type="button" className={`send-btn${canSend ? " on" : ""}${sending ? " busy" : ""}`} disabled={!canSend}
            aria-label={agent ? `Ask @${agent.label}` : "Send"} title={agent ? "Ask" : "Send"} onClick={send}>
            <SendIcon />
          </button>
        </div>
      </div>
    </section>
  );
}

const GROUP_GAP = 5 * 60_000;

/** Day dividers and sender groups: the name shows on a group's first bubble, avatar and time on its last. */
function layout(messages: MessageRecord[]) {
  /** The day a message was sent. */
  const dayOf = (m: MessageRecord) => new Date(m.at).toDateString();
  /** Whether two messages belong to one group. */
  const same = (a: MessageRecord | undefined, b: MessageRecord | undefined) =>
    !!a && !!b && a.sender === b.sender && !a.agent === !b.agent && dayOf(a) === dayOf(b)
    && Math.abs(Date.parse(b.at) - Date.parse(a.at)) < GROUP_GAP;
  return messages.map((m, i) => {
    const prev = messages[i - 1];
    const next = messages[i + 1];
    return {
      m,
      own: m.mine && !m.agent,
      day: !prev || dayOf(prev) !== dayOf(m) ? dayLabel(new Date(m.at)) : null,
      first: !same(prev, m),
      last: !same(m, next),
    };
  });
}

/** Message text: ``` fenced blocks become code blocks with a Copy button, `ticks` inline code; everything else stays plain text (React escapes it). */
function MessageText({ text }: { text: string }) {
  const parts = text.split(/```([\w+#.-]*)\n?([\s\S]*?)```/g);
  const out: React.ReactNode[] = [];
  for (let i = 0; i < parts.length; i += 3) {
    const plain = parts[i].replace(/^\n+|\n+$/g, "");
    if (plain) out.push(<Inline key={i} text={plain} />);
    if (i + 2 < parts.length) out.push(<CodeBlock key={i + 1} lang={parts[i + 1]} code={parts[i + 2].replace(/\n$/, "")} />);
  }
  return <div className="bubble-text">{out}</div>;
}

/** Text with inline code. */
function Inline({ text }: { text: string }) {
  return (
    <span>
      {text.split(/(`[^`\n]+`)/g).map((b, i) =>
        b.length > 2 && b.startsWith("`") && b.endsWith("`") ? <code key={i} className="code-inline">{b.slice(1, -1)}</code> : <Fragment key={i}>{b}</Fragment>,
      )}
    </span>
  );
}

/** A code block with a Copy button. */
function CodeBlock({ lang, code }: { lang: string; code: string }) {
  const { toast } = useApp();
  return (
    <div className="msg-code">
      <div className="msg-code-head">
        <span>{lang || "code"}</span>
        <button type="button" onClick={() => navigator.clipboard.writeText(code).then(() => toast("Copied"), () => toast("Could not copy", true))}>
          <CopyIcon size={13} /> Copy
        </button>
      </div>
      <pre><code>{code}</code></pre>
    </div>
  );
}

/** Today, Yesterday or the date. */
function dayLabel(d: Date) {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short", ...(d.getFullYear() === today.getFullYear() ? {} : { year: "numeric" }) });
}

/** A file in a message: photos and videos show in the chat, other files download. */
function FileView({ conversationId, file }: { conversationId: string; file: Attachment }) {
  const { toast } = useApp();
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const media = file.kind === "image" || file.kind === "video";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const out = await api<{ url: string }>(`/conversations/${conversationId}/files/${file.id}`);
      setUrl(out.url);
      return out.url;
    } catch (e) {
      toast(e instanceof Error ? e.message : "Could not open the file", true);
      return null;
    } finally {
      setLoading(false);
    }
  }, [conversationId, file.id, toast]);

  useEffect(() => { if (media) void load(); }, [media, load]);

  /** Open the file in a new tab. */
  async function download() {
    const u = await load();
    if (u) window.open(u, "_blank", "noopener");
  }

  if (file.kind === "image" && url) return <img className="chat-image" src={url} alt={file.filename} />;
  if (file.kind === "video" && url) return <video className="chat-image" src={url} controls playsInline />;
  return (
    <button type="button" className="file-chip chat-file" onClick={download} disabled={loading}>
      {media ? "⏳" : "📄"} <span>{file.filename}</span> <span className="hint">{loading ? "opening…" : sizeLabel(file.size_bytes)}</span>
    </button>
  );
}
