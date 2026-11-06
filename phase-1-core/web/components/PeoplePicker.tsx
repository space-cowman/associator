"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Avatar } from "./Avatar";

/** Find people by handle; each pick becomes a removable chip. */
export function PeoplePicker({
  picked,
  onChange,
  max = 49,
  exclude = [],
}: {
  picked: string[];
  onChange: (handles: string[]) => void;
  max?: number;
  exclude?: string[];
}) {
  const [q, setQ] = useState("");
  const [found, setFound] = useState<string[]>([]);
  const query = q.trim().toLowerCase().replace(/^@/, "");

  useEffect(() => {
    if (!/^[a-z0-9-]{2,30}$/.test(query)) return setFound([]);
    const t = setTimeout(() => {
      api<string[]>(`/people?q=${encodeURIComponent(query)}`).then(setFound).catch(() => setFound([]));
    }, 250);
    return () => clearTimeout(t);
  }, [query]);

  const options = found.filter((h) => !picked.includes(h) && !exclude.includes(h));
  const full = picked.length >= max;

  return (
    <div className="stack" style={{ gap: 8 }}>
      {picked.length > 0 && (
        <div className="row">
          {picked.map((h) => (
            <span key={h} className="person-chip">
              <Avatar handle={h} size={18} />@{h}
              <button aria-label={`Remove @${h}`} onClick={() => onChange(picked.filter((x) => x !== h))}>×</button>
            </span>
          ))}
        </div>
      )}
      {!full && (
        <input
          className="input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search by handle"
          aria-label="Search people by handle"
          autoComplete="off"
        />
      )}
      {!full && options.length > 0 && (
        <div className="picker-list" role="listbox">
          {options.map((h) => (
            <button key={h} role="option" aria-selected={false} className="picker-item" onClick={() => { onChange([...picked, h]); setQ(""); }}>
              <Avatar handle={h} />@{h}
            </button>
          ))}
        </div>
      )}
      {!full && query.length >= 2 && options.length === 0 && found.length === 0 && <span className="hint">No one found</span>}
    </div>
  );
}
