import Link from "next/link";
import { LEGAL } from "@/lib/legal";
import { Shell } from "./Shell";

/** Shared layout for the Terms and Privacy Policy: title, version, readable text width. */
export function LegalPage({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Shell>
      <article className="card pad legal rise">
        <h1 className="page-title">{title}</h1>
        <p className="hint">Effective {LEGAL.effective} · version {LEGAL.version} · <Link href="/terms">Terms</Link> · <Link href="/privacy">Privacy</Link></p>
        {children}
      </article>
    </Shell>
  );
}
