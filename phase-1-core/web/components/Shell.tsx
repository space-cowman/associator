"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { hueColor } from "@/lib/colors";
import { useApp } from "./Providers";
import { HomeIcon } from "./Icons";

/** Popular icon. */
function FlameIcon() {
  return (<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3c1 4 5 5 5 10a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3-1-3 0-6 1-9z" /></svg>);
}
/** Clusters icon. */
function ClustersIcon() {
  return (<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="7" r="3" /><circle cx="5" cy="17" r="3" /><circle cx="19" cy="17" r="3" /><path d="M10 9.5 6.5 14.5M14 9.5l3.5 5M8 17h8" /></svg>);
}
/** Messages icon. */
function MessagesIcon() {
  return (<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.6A8 8 0 1 1 21 12z" /><path d="M8.5 10.5h7M8.5 13.5h4.5" /></svg>);
}
/** Agents icon. */
function AgentsIcon() {
  return (<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="4" y="8" width="16" height="12" rx="3" /><path d="M12 4v4M9 14h.01M15 14h.01" /></svg>);
}

/** The three main destinations, icons only (names in tooltips and for screen readers): private clusters · messages · agents. */
function MainTabs({ variant }: { variant: "side" | "bottom" | "rail" }) {
  const path = usePathname();
  const tabs = [
    { href: "/private", label: "Clusters", icon: <ClustersIcon />, on: path.startsWith("/private") },
    { href: "/messages", label: "Messages", icon: <MessagesIcon />, on: path.startsWith("/messages") },
    { href: "/settings", label: "Agents", icon: <AgentsIcon />, on: path.startsWith("/settings") || path.startsWith("/drafts") },
  ];
  return (
    <div className={variant === "bottom" ? "tabbar-inner" : `icon-tabs${variant === "rail" ? " rail" : ""}`}>
      {tabs.map((t) => (
        <Link key={t.href} href={t.href} className={`icon-tab${t.on ? " active" : ""}`} title={t.label} aria-label={t.label} aria-current={t.on ? "page" : undefined}>
          {t.icon}
        </Link>
      ))}
    </div>
  );
}

/** Explore icon. */
function CompassIcon() {
  return (<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="m15.5 8.5-2 5-5 2 2-5z" /></svg>);
}

/** A cluster's colored letter. */
function GroupDot({ slug }: { slug: string }) {
  return <span className="group-dot" style={{ background: hueColor(slug) }}>{slug[0]?.toUpperCase()}</span>;
}

/** The phone menu. */
function Nav() {
  const { groups, session } = useApp();
  const path = usePathname();
  const params = useSearchParams();
  const hot = path === "/" && (params.get("sort") ?? "hot") === "hot";
  /** Close the phone menu. */
  const close = () => document.querySelector(".leftnav")?.classList.remove("open");
  const mine = groups.filter((g) => g.joined);
  return (
    <nav className="leftnav" aria-label="Navigation" onClick={close}>
      <MainTabs variant="side" />
      <div className="nav-label">Domain</div>
      <Link href="/?sort=new" className={`nav-item${path === "/" && !hot ? " active" : ""}`}><HomeIcon /> Latest</Link>
      <Link href="/?sort=hot" className={`nav-item${hot ? " active" : ""}`}><FlameIcon /> Popular</Link>
      <Link href="/clusters" className={`nav-item${path === "/clusters" ? " active" : ""}`}><CompassIcon /> Explore clusters</Link>
      {session && (
        <>
          <div className="nav-label">Your clusters</div>
          {mine.map((g) => (
            <Link key={g.id} href={`/c/${g.slug}`} className={`nav-item${path === `/c/${g.slug}` ? " active" : ""}`}>
              <GroupDot slug={g.slug} />{g.slug}
            </Link>
          ))}
          {mine.length === 0 && <div className="hint" style={{ padding: "2px 12px 6px" }}>Join clusters to see them here</div>}
        </>
      )}
      <div className="nav-label">All clusters</div>
      {groups.filter((g) => !g.joined || !session).slice(0, 12).map((g) => (
        <Link key={g.id} href={`/c/${g.slug}`} className={`nav-item${path === `/c/${g.slug}` ? " active" : ""}`}>
          <GroupDot slug={g.slug} />{g.slug}
        </Link>
      ))}
    </nav>
  );
}

/** Slim icon rail for full-width pages (an open chat), like Discord's: the main tabs, the feeds, then your clusters as dots. */
function IconRail() {
  const { groups, session } = useApp();
  const path = usePathname();
  const mine = session ? groups.filter((g) => g.joined) : [];
  return (
    <nav className="icon-rail" aria-label="Navigation">
      <MainTabs variant="rail" />
      <span className="rail-sep" />
      <Link href="/?sort=new" className="icon-tab" title="Latest" aria-label="Latest"><HomeIcon /></Link>
      <Link href="/?sort=hot" className="icon-tab" title="Popular" aria-label="Popular"><FlameIcon /></Link>
      <Link href="/clusters" className={`icon-tab${path === "/clusters" ? " active" : ""}`} title="Explore clusters" aria-label="Explore clusters"><CompassIcon /></Link>
      {mine.length > 0 && <span className="rail-sep" />}
      {mine.map((g) => (
        <Link key={g.id} href={`/c/${g.slug}`} className="rail-dot" title={g.slug} aria-label={g.slug}><GroupDot slug={g.slug} /></Link>
      ))}
    </nav>
  );
}

/** Full-width columns: icon rail · content · side panel (hidden on smaller screens). */
export function Shell({ children, rail, wide = false }: { children: React.ReactNode; rail?: React.ReactNode; wide?: boolean }) {
  const path = usePathname();
  return (
    <div className={`shell${wide ? " wide" : ""}`}>
      <IconRail />
      <Suspense fallback={<nav className="leftnav" />}><Nav /></Suspense>
      <main className="main page-in" key={path}>{children}</main>
      <nav className="tabbar" aria-label="Main"><MainTabs variant="bottom" /></nav>
      {!wide && (
        <aside className="rail" aria-label="About">
          {rail}
          <div className="foot">
            Associator · beta · every AI answer is approved by a person
            <div><Link href="/terms">Terms</Link> · <Link href="/privacy">Privacy</Link></div>
          </div>
        </aside>
      )}
    </div>
  );
}
