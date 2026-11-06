import Link from "next/link";
import { PlusIcon } from "./Icons";

/** Right-panel card: what this place is (or this group), and the main action. */
export function AskCard({ title, text, group }: { title: string; text: string; group?: string }) {
  return (
    <div className="card pad stack" style={{ gap: 10 }}>
      <div>
        <div className={group ? "rail-group" : "rail-title"}>{title}</div>
        <div className="hint" style={{ color: "var(--ink-2)" }}>{text}</div>
      </div>
      <Link href={group ? `/submit?group=${group}` : "/submit"} className="btn primary block">
        <PlusIcon size={15} /> Post a question
      </Link>
    </div>
  );
}
