"use client";

import { useParams } from "next/navigation";
import { Suspense } from "react";
import { AskCard } from "@/components/AskCard";
import { Feed } from "@/components/Feed";
import { GroupHeader } from "@/components/GroupHeader";
import { useApp } from "@/components/Providers";
import { Shell } from "@/components/Shell";

/** A cluster's page with its questions. */
export default function ClusterPage() {
  const { slug } = useParams<{ slug: string }>();
  const { groups } = useApp();
  const group = groups.find((g) => g.slug === slug);
  return (
    <Shell rail={<AskCard title={group?.name ?? slug} group={slug} text={group?.description ?? "Ask the people in this cluster."} />}>
      <GroupHeader slug={slug} />
      <Suspense fallback={<div className="skeleton" />}>
        <Feed path={`/groups/${slug}/threads`} empty={<div className="big">No questions here yet</div>} />
      </Suspense>
    </Shell>
  );
}
