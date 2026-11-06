"""SimilarThreads: one retrieval, two users."""

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from api.visibility import VISIBLE_TO_VIEWER

_QUERY = text(
    f"""
    WITH q AS (
      SELECT replace(plainto_tsquery('english', :text)::text, '&', '|')::tsquery AS query
    )
    SELECT t.id, g.slug AS group_slug, t.text,
           t.satisfied_reply_id IS NOT NULL AS answered
    FROM threads t
    JOIN topic_groups g ON g.id = t.group_id
    CROSS JOIN q
    WHERE t.search @@ q.query
      AND t.deleted_at IS NULL
      AND (CAST(:exclude_id AS uuid) IS NULL OR t.id <> CAST(:exclude_id AS uuid))
      AND (NOT :answered_only OR t.satisfied_reply_id IS NOT NULL)
      AND {VISIBLE_TO_VIEWER}
    ORDER BY ts_rank_cd(t.search, q.query) DESC, t.created_at DESC
    LIMIT :limit
    """  # noqa: S608
)


@dataclass(frozen=True)
class SimilarThread:
    id: uuid.UUID
    group_slug: str
    text: str
    answered: bool


async def find_similar(
    conn: AsyncConnection,
    query_text: str,
    *,
    limit: int = 5,
    exclude_id: uuid.UUID | None = None,
    answered_only: bool = False,
    viewer: uuid.UUID | None = None,
) -> list[SimilarThread]:
    """Find questions similar to a text."""
    rows = await conn.execute(
        _QUERY,
        {
            "text": query_text,
            "limit": limit,
            "exclude_id": exclude_id,
            "answered_only": answered_only,
            "viewer": viewer,
        },
    )
    return [SimilarThread(**row._mapping) for row in rows]
