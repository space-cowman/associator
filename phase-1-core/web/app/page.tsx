"use client";

import Link from "next/link";
import { Suspense } from "react";
import { AskCard } from "@/components/AskCard";
import { Feed } from "@/components/Feed";
import { Shell } from "@/components/Shell";

/** The home feed. */
export default function Home() {
  return (
    <Shell
      rail={
        <AskCard
          title="Associator"
          text="Not happy with your AI's answer? Ask here. People answer themselves or with their own AI — every AI answer is approved by a person first."
        />
      }
    >
      <div>
        <h1 className="page-title">All clusters</h1>
        <p className="page-sub">Threads from every public cluster</p>
      </div>
      <Suspense fallback={<div className="skeleton" />}>
        <Feed
          path="/threads"
          empty={<><div className="big">No questions yet</div><Link href="/submit" className="hint">Be the first to ask →</Link></>}
        />
      </Suspense>
    </Shell>
  );
}
