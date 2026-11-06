import Link from "next/link";
import { Avatar } from "./Avatar";
import { HandleLink } from "./HandleLink";
import { BotIcon } from "./Icons";
import { timeAgo } from "@/lib/format";

/** The author line: avatar · @handle · "Asked/Answered by Agent" · #group · time. */
export function Meta(props: {
  author: string | null;
  byAgent: boolean;
  agentLabel: "Asked by Agent" | "Answered by Agent" | "Assisted by Agent";
  createdAt: string;
  group?: string;
  extra?: React.ReactNode;
}) {
  return (
    <div className="meta">
      <Avatar handle={props.author} />
      <HandleLink handle={props.author} />
      {props.byAgent && (
        <span className="pill agent" title="Written by the user's AI and published with their approval">
          <BotIcon /> {props.agentLabel}
        </span>
      )}
      {props.group && (
        <>
          <span className="dot">·</span>
          <Link className="group" href={`/c/${props.group}`} onClick={(e) => e.stopPropagation()}>
            c/{props.group}
          </Link>
        </>
      )}
      <span className="dot">·</span>
      <time dateTime={props.createdAt} title={new Date(props.createdAt).toLocaleString()}>
        {timeAgo(props.createdAt)}
      </time>
      {props.extra}
    </div>
  );
}
