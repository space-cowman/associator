"""Who may see a cluster's content."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

VISIBLE_TO_VIEWER = (
    "(NOT g.hidden OR EXISTS (SELECT 1 FROM group_members gm"
    " WHERE gm.group_id = g.id AND gm.user_id = CAST(:viewer AS uuid)))"
)


async def ensure_visible(
    conn: AsyncConnection,
    viewer: uuid.UUID | None,
    *,
    thread_id: uuid.UUID | None = None,
    reply_id: uuid.UUID | None = None,
    slug: str | None = None,
) -> None:
    """404 unless the thread / reply / cluster exists and its cluster is visible to the viewer."""
    if thread_id is not None:
        sql = "SELECT 1 FROM threads t JOIN topic_groups g ON g.id = t.group_id WHERE t.id = :k"
        key: object = thread_id
    elif reply_id is not None:
        sql = (
            "SELECT 1 FROM replies r JOIN threads t ON t.id = r.thread_id"
            " JOIN topic_groups g ON g.id = t.group_id WHERE r.id = :k"
        )
        key = reply_id
    else:
        sql = "SELECT 1 FROM topic_groups g WHERE g.slug = :k"
        key = slug
    found = await conn.scalar(
        text(f"{sql} AND {VISIBLE_TO_VIEWER}"),  # noqa: S608
        {"k": key, "viewer": viewer},
    )
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
