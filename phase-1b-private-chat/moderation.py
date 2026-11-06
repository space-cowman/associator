"""Owner tools for private chats (run through make; needs make db-tunnel; owner role)."""

import json
import os
import sys
import uuid

import boto3  # type: ignore[import-untyped]
import psycopg


def db() -> psycopg.Connection:
    """Connect to the database as the owner."""
    return psycopg.connect(
        host="127.0.0.1",
        port=15432,
        dbname="platform_v2",
        user="platform_v2_owner",
        password=os.environ["PGPASSWORD"],
    )


def reports() -> None:
    """List open reports, summary only."""
    with db() as conn:
        rows = conn.execute(
            "SELECT id, created_at, reason, reported_handle, jsonb_array_length(content),"
            " CASE WHEN reply_id IS NOT NULL THEN 'reply'"
            " WHEN thread_id IS NOT NULL THEN 'question' ELSE 'private chat' END"
            " FROM reports WHERE status = 'open' ORDER BY created_at"
        ).fetchall()
    print(f"{len(rows)} open report(s)")
    for rid, at, reason, who, n, where in rows:
        when = f"{at:%Y-%m-%d %H:%M}"
        print(f"  {rid}  {when}  {where:<12}  {reason:<10}  @{who or '-'}  {n} message(s)")


def report(rid: str) -> None:
    """Show one report in full."""
    with db() as conn:
        row = conn.execute(
            "SELECT r.created_at, r.reason, r.reported_handle, r.details, r.content, r.status,"
            " u.handle FROM reports r LEFT JOIN users u ON u.id = r.reporter_id WHERE r.id = %s",
            (uuid.UUID(rid),),
        ).fetchone()
    if row is None:
        sys.exit("no such report")
    at, reason, who, details, content, state, reporter = row
    print(f"{at:%Y-%m-%d %H:%M} · {reason} · reported @{who or '-'} by @{reporter} · {state}")
    if details:
        print(f"details: {details}")
    print(json.dumps(content, indent=2, ensure_ascii=False))


def close(rid: str, outcome: str) -> None:
    """Close a report."""
    if outcome not in ("actioned", "dismissed"):
        sys.exit("status must be actioned or dismissed")
    with db() as conn:
        done = conn.execute(
            "UPDATE reports SET status = %s WHERE id = %s AND status = 'open'",
            (outcome, uuid.UUID(rid)),
        ).rowcount
    print("closed" if done else "no open report with that id")


REMOVED = "[Removed by moderators]"


def remove(rid: str) -> None:
    """Hide a reported public post and close the report."""
    with db() as conn:
        row = conn.execute(
            "SELECT thread_id, reply_id, status FROM reports WHERE id = %s", (uuid.UUID(rid),)
        ).fetchone()
        if row is None:
            sys.exit("no such report")
        thread_id, reply_id, state = row
        if reply_id is not None:
            conn.execute("UPDATE replies SET text = %s WHERE id = %s", (REMOVED, reply_id))
            what = "reply text replaced"
        elif thread_id is not None:
            conn.execute(
                "UPDATE threads SET deleted_at = now() WHERE id = %s AND deleted_at IS NULL",
                (thread_id,),
            )
            what = "question hidden"
        else:
            sys.exit("a private-chat report: remove the person from the chat or block instead")
        conn.execute("UPDATE reports SET status = 'actioned' WHERE id = %s", (uuid.UUID(rid),))
    print(f"{what}; report closed as actioned (was {state})")


def sweep(confirm: bool) -> None:
    """Delete the old end-to-end encrypted chat files."""
    bucket = os.environ["ATTACHMENTS_BUCKET"]
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-south-1"))
    keys: list[str] = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="e2e/"):
        keys += [o["Key"] for o in page.get("Contents", [])]
    print(f"{len(keys)} old encrypted chat file(s)")
    if keys and confirm:
        for i in range(0, len(keys), 1000):
            s3.delete_objects(
                Bucket=bucket, Delete={"Objects": [{"Key": k} for k in keys[i : i + 1000]]}
            )
        print(f"deleted {len(keys)}")
    elif keys:
        print("nothing deleted (run with confirm=1 to delete them)")


if __name__ == "__main__":
    command, *args = sys.argv[1:] or ["reports"]
    if command == "reports":
        reports()
    elif command == "report" and len(args) == 1:
        report(args[0])
    elif command == "close" and len(args) == 2:
        close(args[0], args[1])
    elif command == "remove" and len(args) == 1:
        remove(args[0])
    elif command == "sweep":
        sweep("--confirm" in args)
    else:
        sys.exit(__doc__)
