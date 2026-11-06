"""Removes everything the load test created."""

import json
import os
import sys
from pathlib import Path

import psycopg

EXPECTED_SYSTEM_ID = 7701263628382191654
MANIFEST = Path(os.environ.get("LOADGEN_MANIFEST", ".secrets/loadgen/manifest.json"))


def main() -> None:
    """Delete everything the load test created."""
    if not MANIFEST.exists():
        sys.exit("nothing to clean: no manifest")
    m = json.loads(MANIFEST.read_text())
    ids = [p["id"] for p in m["people"]]
    slugs = [c.split("|")[1] for c in m["clusters"]]
    with psycopg.connect(
        host="127.0.0.1",
        port=15432,
        dbname="platform_v2",
        user="platform_v2_owner",
        password=os.environ["PG_OWNER_PASSWORD"],
    ) as conn:
        found = conn.execute("SELECT system_identifier FROM pg_control_system()").fetchone()
        if found is None or found[0] != EXPECTED_SYSTEM_ID:
            sys.exit("not the expected database: nothing deleted")
        replies = conn.execute(
            "DELETE FROM replies WHERE author_id = ANY(%s::uuid[])", (ids,)
        ).rowcount
        threads = conn.execute(
            "DELETE FROM threads WHERE author_id = ANY(%s::uuid[])", (ids,)
        ).rowcount
        clusters = conn.execute(
            "DELETE FROM topic_groups g WHERE g.slug = ANY(%s)"
            " AND NOT EXISTS (SELECT 1 FROM threads t WHERE t.group_id = g.id)",
            (slugs,),
        ).rowcount
        kept = conn.execute(
            "SELECT slug FROM topic_groups WHERE slug = ANY(%s)", (slugs,)
        ).fetchall()
        people = conn.execute("DELETE FROM users WHERE id = ANY(%s::uuid[])", (ids,)).rowcount
    print(f"deleted {people} people, {threads} threads, {replies} replies, {clusters} clusters")
    if kept:
        print("kept (someone else posted there):", ", ".join(k[0] for k in kept))
    MANIFEST.rename(MANIFEST.with_suffix(".cleaned.json"))


if __name__ == "__main__":
    main()
