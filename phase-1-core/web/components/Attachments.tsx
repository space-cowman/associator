"use client";

import { useEffect, useState } from "react";
import type { Attachment } from "@/lib/types";
import { WarnIcon } from "./Icons";

/** A file size in KB or MB. */
function size(bytes: number): string {
  return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** Images in a grid, videos with controls, PDFs and text files as download chips. */
function Lightbox({ src, alt, onClose }: { src: string; alt: string; onClose: () => void }) {
  useEffect(() => {
    /** Close on Escape. */
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  return (
    <div className="lightbox" role="dialog" aria-label={alt} onClick={onClose}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={alt} />
      <button className="lightbox-x" aria-label="Close">×</button>
    </div>
  );
}

/** The files on a post. */
export function Attachments({ items }: { items: Attachment[] }) {
  const [zoom, setZoom] = useState<Attachment | null>(null);
  if (!items.length) return null;
  const media = items.filter((a) => a.kind === "image" || a.kind === "video");
  const docs = items.filter((a) => a.kind === "pdf" || a.kind === "text");
  return (
    <div className="attachments" onClick={(e) => e.stopPropagation()}>
      {media.length > 0 && (
        <div className={`media-grid n${Math.min(media.length, 4)}`}>
          {media.map((a) =>
            a.kind === "image" ? (
              <a key={a.id} href={`/api/attachments/${a.id}`} className="media" onClick={(e) => { e.preventDefault(); setZoom(a); }}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={`/api/attachments/${a.id}`} alt={a.filename} loading="lazy" />
              </a>
            ) : (
              <video key={a.id} className="media" src={`/api/attachments/${a.id}`} controls preload="metadata" />
            ),
          )}
        </div>
      )}
      {zoom && <Lightbox src={`/api/attachments/${zoom.id}`} alt={zoom.filename} onClose={() => setZoom(null)} />}
      {docs.map((a) => (
        <a key={a.id} className="file-chip" href={`/api/attachments/${a.id}`} rel="noopener noreferrer" download={a.filename}>
          <span className="file-kind">{a.kind === "pdf" ? "PDF" : "TXT"}</span>
          <span className="file-name">{a.filename}</span>
          <span className="hint">{size(a.size_bytes)}</span>
        </a>
      ))}
    </div>
  );
}

/** Safety labels for code inside a post. */
export function Warnings({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="warnings">
      {items.map((w) => (
        <div className="warning" key={w}><WarnIcon /> {w}</div>
      ))}
    </div>
  );
}
