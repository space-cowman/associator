"use client";

import { useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Attachment } from "@/lib/types";

export const LIMIT = 500;
const MB = 1024 * 1024;
const MAX_FILES = 4;
export const ALLOWED: Record<string, number> = {
  "image/png": 5 * MB,
  "image/jpeg": 5 * MB,
  "image/webp": 5 * MB,
  "image/gif": 5 * MB,
  "application/pdf": 5 * MB,
  "text/plain": 1 * MB,
  "video/mp4": 25 * MB,
  "video/webm": 25 * MB,
};

export type Upload = {
  key: string;
  name: string;
  type: string;
  preview: string | null;
  progress: number;
  status: "uploading" | "ready" | "error";
  error?: string;
  attachment?: Attachment;
};

type UploadForm = { id: string; url: string; fields: Record<string, string> };

/** Upload a file with the signed form. */
function sendToStorage(form: UploadForm, file: File, onProgress: (p: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const body = new FormData();
    Object.entries(form.fields).forEach(([k, v]) => body.append(k, v));
    body.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", form.url);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => (xhr.status < 300 ? resolve() : reject(new Error("Upload refused by storage")));
    xhr.onerror = () => reject(new Error("Upload failed"));
    xhr.send(body);
  });
}

/** Upload one file through the checked pipeline (signed form, then the api checks it) and return the attachment, ready to put on a post or a chat message. */
export async function uploadAttachment(file: File, onProgress: (p: number) => void = () => undefined): Promise<Attachment> {
  const form = await api<UploadForm>("/uploads", {
    method: "POST",
    body: { filename: file.name, content_type: file.type, size_bytes: file.size },
  });
  await sendToStorage(form, file, onProgress);
  return api<Attachment>(`/uploads/${form.id}/complete`, { method: "POST" });
}

type Action = "bold" | "italic" | "strike" | "code" | "block" | "list" | "numbered" | "link";
const TOOLS: { action: Action; label: string; title: string }[] = [
  { action: "bold", label: "B", title: "Bold (**text**)" },
  { action: "italic", label: "I", title: "Italic (*text*)" },
  { action: "strike", label: "S", title: "Strikethrough (~~text~~)" },
  { action: "code", label: "</>", title: "Inline code (`code`)" },
  { action: "block", label: "{ }", title: "Code block (```)" },
  { action: "list", label: "•", title: "Bulleted list" },
  { action: "numbered", label: "1.", title: "Numbered list" },
  { action: "link", label: "🔗", title: "Link" },
];

/** Text box with a formatting toolbar, a 500-character counter and optional attachments. */
export function Editor(props: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  minHeight?: number;
  autoFocus?: boolean;
  uploads?: Upload[];
  onUploads?: (u: Upload[] | ((old: Upload[]) => Upload[])) => void;
  label?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [fileError, setFileError] = useState("");

  /** Apply a formatting button. */
  function apply(action: Action) {
    const el = ref.current;
    if (!el) return;
    const { selectionStart: a, selectionEnd: b, value } = el;
    const picked = value.slice(a, b);
    const wrap: Record<string, [string, string, string]> = {
      bold: ["**", "**", "bold text"],
      italic: ["*", "*", "italic text"],
      strike: ["~~", "~~", "struck text"],
      code: ["`", "`", "code"],
      block: ["```\n", "\n```", "code"],
      link: ["[", "](https://)", "link text"],
    };
    let next: string;
    let caretFrom: number;
    let caretTo: number;
    if (action === "list" || action === "numbered") {
      const text = picked || "item";
      const lines = text.split("\n").map((l, i) => (action === "list" ? `- ${l}` : `${i + 1}. ${l}`));
      const lead = a > 0 && value[a - 1] !== "\n" ? "\n" : "";
      const inserted = lead + lines.join("\n");
      next = value.slice(0, a) + inserted + value.slice(b);
      caretFrom = a + lead.length;
      caretTo = a + inserted.length;
    } else {
      const [pre, post, sample] = wrap[action];
      const inner = picked || sample;
      next = value.slice(0, a) + pre + inner + post + value.slice(b);
      caretFrom = a + pre.length;
      caretTo = caretFrom + inner.length;
    }
    props.onChange(next);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(caretFrom, caretTo);
    });
  }

  /** Upload the chosen files. */
  async function addFiles(list: FileList | null) {
    if (!list || !props.onUploads) return;
    setFileError("");
    const current = props.uploads ?? [];
    const files = Array.from(list).slice(0, MAX_FILES - current.length);
    if (list.length > files.length) setFileError(`At most ${MAX_FILES} files per post`);
    for (const file of files) {
      const max = ALLOWED[file.type];
      if (!max) {
        setFileError("Allowed: images (PNG, JPEG, WebP, GIF), PDF, plain text, MP4/WebM video");
        continue;
      }
      if (file.size > max) {
        setFileError(`${file.name}: at most ${max / MB} MB for this type`);
        continue;
      }
      const key = `${file.name}-${file.size}-${Math.random()}`;
      const preview = file.type.startsWith("image/") ? URL.createObjectURL(file) : null;
      const item: Upload = { key, name: file.name, type: file.type, preview, progress: 0, status: "uploading" };
      props.onUploads((old) => [...old, item]);
      /** Update one upload's progress. */
      const update = (patch: Partial<Upload>) =>
        props.onUploads?.((old) => old.map((u) => (u.key === key ? { ...u, ...patch } : u)));
      try {
        const form = await api<UploadForm>("/uploads", {
          method: "POST",
          body: { filename: file.name, content_type: file.type, size_bytes: file.size },
        });
        await sendToStorage(form, file, (p) => update({ progress: p }));
        const attachment = await api<Attachment>(`/uploads/${form.id}/complete`, { method: "POST" });
        update({ status: "ready", progress: 1, attachment });
      } catch (e) {
        update({ status: "error", error: e instanceof ApiError || e instanceof Error ? e.message : "Upload failed" });
      }
    }
    if (fileRef.current) fileRef.current.value = "";
  }

  const over = props.value.length > LIMIT;
  const uploads = props.uploads ?? [];
  return (
    <div className="editor">
      <div className="toolbar" role="toolbar" aria-label="Formatting">
        {TOOLS.map((t) => (
          <button key={t.action} type="button" className={`tool tool-${t.action}`} title={t.title} aria-label={t.title} onClick={() => apply(t.action)}>
            {t.label}
          </button>
        ))}
        {props.onUploads && (
          <>
            <span className="tool-sep" />
            <button type="button" className="tool" title="Attach images, PDF, text or video" aria-label="Attach files" disabled={uploads.length >= MAX_FILES} onClick={() => fileRef.current?.click()}>
              📎
            </button>
            <input ref={fileRef} type="file" hidden multiple accept={Object.keys(ALLOWED).join(",")} onChange={(e) => void addFiles(e.target.files)} />
          </>
        )}
      </div>
      <textarea
        ref={ref}
        className="textarea editor-area"
        style={{ minHeight: props.minHeight ?? 96 }}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        placeholder={props.placeholder}
        autoFocus={props.autoFocus}
        aria-label={props.label ?? "Text"}
      />
      {uploads.length > 0 && (
        <div className="upload-row">
          {uploads.map((u) => (
            <div key={u.key} className={`upload ${u.status}`} title={u.error ?? u.name}>
              {u.preview ? <img src={u.preview} alt="" /> : <span className="file-kind">{u.type.split("/")[1]?.slice(0, 4).toUpperCase()}</span>}
              <span className="upload-name">{u.name}</span>
              {u.status === "uploading" && <span className="bar"><span style={{ width: `${Math.round(u.progress * 100)}%` }} /></span>}
              {u.status === "error" && <span className="error" style={{ fontSize: 12 }}>{u.error}</span>}
              <button type="button" className="upload-x" aria-label={`Remove ${u.name}`} onClick={() => props.onUploads?.((old) => old.filter((x) => x.key !== u.key))}>×</button>
            </div>
          ))}
        </div>
      )}
      {fileError && <div className="error">{fileError}</div>}
      <div className={`counter${over ? " over" : ""}`}>{props.value.length}/{LIMIT} · formatting and code count too</div>
    </div>
  );
}

/** The ids of finished uploads. */
export function readyIds(uploads: Upload[]): string[] {
  return uploads.filter((u) => u.status === "ready" && u.attachment).map((u) => u.attachment!.id);
}

/** Whether any upload is still running. */
export function stillUploading(uploads: Upload[]): boolean {
  return uploads.some((u) => u.status === "uploading");
}
