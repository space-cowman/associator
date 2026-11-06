"""Attachments on posts: linking checked uploads to a question or answer, and loading them."""

import uuid
from collections import defaultdict
from typing import Annotated

from fastapi import HTTPException, status
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

MAX_PER_POST = 4


def _distinct(ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """Check that no attachment id is listed twice."""
    if len(set(ids)) != len(ids):
        raise ValueError("the same attachment is listed twice")
    return ids


AttachmentIds = Annotated[
    list[uuid.UUID], Field(max_length=MAX_PER_POST), AfterValidator(_distinct)
]


class AttachmentOut(BaseModel):
    id: uuid.UUID
    kind: str
    filename: str
    content_type: str
    size_bytes: int


async def link(
    conn: AsyncConnection,
    owner_id: uuid.UUID,
    ids: list[uuid.UUID],
    *,
    thread_id: uuid.UUID | None = None,
    reply_id: uuid.UUID | None = None,
) -> list[AttachmentOut]:
    """Attach the person's checked uploads to a post."""
    out: list[AttachmentOut] = []
    for position, attachment_id in enumerate(ids):
        row = (
            await conn.execute(
                text(
                    "UPDATE attachments SET thread_id = :t, reply_id = :r, position = :p"
                    " WHERE id = :id AND owner_id = :u AND status = 'ready'"
                    " AND thread_id IS NULL AND reply_id IS NULL"
                    " RETURNING id, kind, filename, content_type, size_bytes"
                ),
                {"t": thread_id, "r": reply_id, "p": position, "id": attachment_id, "u": owner_id},
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "An attachment is not ready or not available"
            )
        out.append(AttachmentOut(**row._mapping))
    return out


async def load(
    conn: AsyncConnection, column: str, post_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[AttachmentOut]]:
    """Attachments for many questions (column 'thread_id') or answers ('reply_id') at once."""
    if column not in ("thread_id", "reply_id"):
        raise ValueError(column)
    found: dict[uuid.UUID, list[AttachmentOut]] = defaultdict(list)
    if not post_ids:
        return found
    rows = await conn.execute(
        text(
            f"SELECT {column} AS post_id, id, kind, filename, content_type, size_bytes"  # noqa: S608
            f" FROM attachments WHERE {column} = ANY(:ids) ORDER BY {column}, position"
        ),
        {"ids": post_ids},
    )
    for r in rows:
        m = dict(r._mapping)
        found[m.pop("post_id")].append(AttachmentOut(**m))
    return found
