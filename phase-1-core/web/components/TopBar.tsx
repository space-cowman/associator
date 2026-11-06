"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useApp } from "./Providers";
import { Avatar } from "./Avatar";
import { Bell } from "./Bell";
import { InboxIcon, MenuIcon, MoonIcon, PlusIcon, SearchIcon, SunIcon } from "./Icons";

/** The theme and a way to switch it. */
function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState("light");
  useEffect(() => setTheme(document.documentElement.dataset.theme ?? "light"), []);
  /** Switch between dark and light. */
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("pp.theme", next);
    } catch {
    }
    setTheme(next);
  };
  return [theme, toggle];
}

/** The bar at the top of every page. */
export function TopBar() {
  const { session, pendingDrafts, signOut } = useApp();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [menu, setMenu] = useState(false);
  const [theme, toggleTheme] = useTheme();
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    /** Close the phone menu. */
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenu(false);
    };
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, []);

  return (
    <header className="topbar">
      <button
        className="icon-btn menu-btn"
        aria-label="Open clusters"
        onClick={() => document.querySelector(".leftnav")?.classList.toggle("open")}
      >
        <MenuIcon />
      </button>
      <Link href="/" className="brand" aria-label="Associator home">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className="brand-logo on-light" src="/brand/logo-ink.png" alt="" width={40} height={24} />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className="brand-logo on-dark" src="/brand/logo-white.png" alt="" width={40} height={24} />
        <span>Associator</span>
      </Link>
      <form
        className="search"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          if (q.trim()) router.push(`/search?q=${encodeURIComponent(q.trim())}`);
        }}
      >
        <SearchIcon />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search questions" aria-label="Search questions" maxLength={500} />
      </form>
      <div className="top-actions">
        <Link href="/submit" className="btn primary small" aria-label="Ask a question">
          <PlusIcon size={15} /> Ask
        </Link>
        {session && (
          <Link href="/drafts" className="icon-btn" aria-label={`Drafts awaiting approval: ${pendingDrafts}`} title="Drafts awaiting your approval">
            <InboxIcon />
            {pendingDrafts > 0 && <span className="badge">{pendingDrafts}</span>}
          </Link>
        )}
        <Bell />
        <button className="icon-btn" onClick={toggleTheme} aria-label="Toggle light or dark theme" title="Light / dark">
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>
        {session ? (
          <div ref={menuRef} style={{ position: "relative" }}>
            <button className="icon-btn" aria-label="Your account" onClick={() => setMenu((m) => !m)}>
              <Avatar handle={session.handle} size={26} />
            </button>
            {menu && (
              <div className="dropdown" role="menu">
                <div className="hint" style={{ padding: "6px 10px 8px" }}>Signed in as <b>@{session.handle}</b></div>
                <Link href={`/u/${session.handle}`} onClick={() => setMenu(false)}>My profile</Link>
                <Link href="/drafts" onClick={() => setMenu(false)}>My drafts</Link>
                <Link href="/settings" onClick={() => setMenu(false)}>Settings</Link>
                <div className="divider" />
                <button onClick={() => { signOut(); setMenu(false); router.push("/"); }}>Sign out</button>
              </div>
            )}
          </div>
        ) : (
          <Link href="/signin" className="btn small">Sign in</Link>
        )}
      </div>
    </header>
  );
}
