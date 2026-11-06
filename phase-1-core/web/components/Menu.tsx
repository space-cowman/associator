"use client";

import { useEffect, useRef, useState } from "react";

export type MenuItem = { label: string; onSelect: () => void; icon?: React.ReactNode; danger?: boolean };

/** A small popover menu (⋯, ＋): opens next to its button, above it with `up`; a pick, Escape or a click outside closes it. */
export function Menu({ label, icon, items, align = "end", up = false, className = "icon-btn" }: {
  label: string; icon: React.ReactNode; items: MenuItem[]; align?: "start" | "end"; up?: boolean; className?: string;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    /** Close on a click outside. */
    const away = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    /** Close on Escape. */
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", key); };
  }, [open]);
  return (
    <div className="menu" ref={box}>
      <button type="button" className={className} aria-label={label} title={label} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {icon}
      </button>
      {open && (
        <div role="menu" className={`menu-pop ${align}${up ? " up" : ""}`}>
          {items.map((it) => (
            <button type="button" key={it.label} role="menuitem" className={`menu-item${it.danger ? " danger" : ""}`} onClick={() => { setOpen(false); it.onSelect(); }}>
              {it.icon}{it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
