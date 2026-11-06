"""Replies: human replies (signed in, rate-limited) and paged reading."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Row, text
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncConnection

from api import formatting, ratelimit, safety_client
from api.attachments import AttachmentIds, AttachmentOut, link, load
from api.auth import CurrentUser, current_user, optional_user
from api.routes.threads import PostText
from api.routes.votes import COUNT_COLUMNS, VoteCounts, counts_from
from api.visibility import ensure_visible

router = APIRouter()

CREATE_LIMIT = 30
CREATE_WINDOW_SECONDS = 3600
MAX_DEPTH = 50
PAGE_DEFAULT, PAGE_MAX = 50, 100


class ReplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: PostText
    parent_id: uuid.UUID | None = None
    attachments: AttachmentIds = []
    confirm_personal_data: bool = False


Via = Literal["person", "assisted", "agent"]


class ReplyOut(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    parent_id: uuid.UUID | None
    depth: int
    reply_to_id: uuid.UUID | None
    reply_to_author: str | None
    author: str | None
    by_agent: bool
    via: Via
    text: str
    created_at: datetime
    votes: VoteCounts
    warnings: list[str]
    attachments: list[AttachmentOut]


_SELECT = (
    "SELECT r.id, r.thread_id, r.parent_id, r.depth, r.reply_to_id,"  # noqa: S608
    " tu.handle AS reply_to_author, u.handle AS author, r.mode <> 'self' AS by_agent,"
    " CASE r.mode WHEN 'self' THEN 'person' WHEN 'mcp' THEN 'agent' ELSE 'assisted' END AS via,"
    " r.text, r.created_at, r.warnings,"
    " v.human_up, v.human_down, v.agent_up, v.agent_down"
    " FROM replies r"
    " LEFT JOIN users u ON u.id = r.author_id"
    " LEFT JOIN replies t ON t.id = r.reply_to_id"
    " LEFT JOIN users tu ON tu.id = t.author_id"
    f" CROSS JOIN LATERAL (SELECT {COUNT_COLUMNS} FROM votes WHERE reply_id = r.id) v"
)


_VOTE_KEYS = ("human_up", "human_down", "agent_up", "agent_down")


def _out(row: Row[Any], files: list[AttachmentOut]) -> ReplyOut:
    """Shape one reply for the response."""
    m = row._mapping
    fields = {k: v for k, v in m.items() if k not in _VOTE_KEYS}
    return ReplyOut(**fields, votes=counts_from(m), attachments=files)


async def insert_reply(
    conn: AsyncConnection,
    *,
    thread_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    author_id: uuid.UUID,
    text: str,
    mode: str = "self",
    model_label: str | None = None,
    instruction_given: bool = False,
    human_approved: bool = False,
    warnings: list[str] | None = None,
) -> uuid.UUID | None:
    """The one way a reply is stored (human replies and approved AI drafts alike)."""
    row = (
        await conn.execute(
            sql(
                "INSERT INTO replies (thread_id, parent_id, reply_to_id, author_id, text, mode,"
                " model_label, instruction_given, human_approved, warnings, depth)"
                " SELECT t.id,"
                "   CASE WHEN p.depth >= :max THEN p.parent_id ELSE p.id END,"
                "   CASE WHEN p.depth >= :max THEN p.id END,"
                "   :uid, :text, :mode, :label, :instructed, :approved, :warnings,"
                "   LEAST(COALESCE(p.depth + 1, 0), :max)"
                " FROM threads t"
                " LEFT JOIN replies p"
                "   ON p.id = CAST(:parent AS uuid) AND p.thread_id = t.id"
                " WHERE t.id = :thread AND t.deleted_at IS NULL"
                "   AND (CAST(:parent AS uuid) IS NULL OR p.id IS NOT NULL)"
                " RETURNING id"
            ),
            {
                "uid": author_id,
                "text": text,
                "mode": mode,
                "label": model_label,
                "instructed": instruction_given,
                "approved": human_approved,
                "warnings": warnings or [],
                "parent": parent_id,
                "thread": thread_id,
                "max": MAX_DEPTH,
            },
        )
    ).one_or_none()
    if row is None:
        return None
    await conn.execute(
        sql(
            "INSERT INTO notifications (user_id, kind, thread_id, reply_id, actor_id)"
            " SELECT COALESCE(p.author_id, t.author_id), 'reply', r.thread_id, r.id, r.author_id"
            " FROM replies r JOIN threads t ON t.id = r.thread_id"
            " LEFT JOIN replies p ON p.id = COALESCE(r.reply_to_id, r.parent_id)"
            " WHERE r.id = :id AND COALESCE(p.author_id, t.author_id) IS NOT NULL"
            " AND COALESCE(p.author_id, t.author_id) IS DISTINCT FROM r.author_id"
        ),
        {"id": row.id},
    )
    reply_id: uuid.UUID = row.id
    return reply_id


@router.post("/threads/{thread_id}/replies", status_code=status.HTTP_201_CREATED)
async def create_reply(
    thread_id: uuid.UUID,
    body: ReplyIn,
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
) -> ReplyOut:
    """Post a reply."""
    async with request.app.state.db.connect() as conn:
        await ensure_visible(conn, user.id, thread_id=thread_id)
    await ratelimit.enforce(
        request, f"ratelimit:replies:create:{user.id}", CREATE_LIMIT, CREATE_WINDOW_SECONDS
    )
    warnings = await safety_client.check(
        request,
        body.text,
        formatting.for_safety(body.text),
        personal_data="allow" if body.confirm_personal_data else "ask",
    )
    async with request.app.state.db.begin() as conn:
        reply_id = await insert_reply(
            conn,
            thread_id=thread_id,
            parent_id=body.parent_id,
            author_id=user.id,
            text=body.text,
            warnings=formatting.warning_labels(warnings),
        )
        if reply_id is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread or parent reply not found")
        files = await link(conn, user.id, body.attachments, reply_id=reply_id)
        created = (await conn.execute(text(_SELECT + " WHERE r.id = :id"), {"id": reply_id})).one()
    return _out(created, files)


@router.get("/threads/{thread_id}/replies")
async def list_replies(
    thread_id: uuid.UUID,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=PAGE_MAX)] = PAGE_DEFAULT,
    after: uuid.UUID | None = None,
    user: Annotated[CurrentUser | None, Depends(optional_user)] = None,
) -> list[ReplyOut]:
    """Oldest first (conversation order), flat with parent_id + depth; clients build the tree."""
    async with request.app.state.db.connect() as conn:
        await ensure_visible(conn, user.id if user else None, thread_id=thread_id)
    async with request.app.state.db.connect() as conn:
        rows = await conn.execute(
            text(
                _SELECT  # noqa: S608
                + " WHERE r.thread_id = :thread AND (CAST(:after AS uuid) IS NULL"
                " OR (r.created_at, r.id) > (SELECT created_at, id FROM replies"
                " WHERE id = CAST(:after AS uuid)))"
                " ORDER BY r.created_at, r.id LIMIT :limit"
            ),
            {"thread": thread_id, "after": after, "limit": limit},
        )
        page = list(rows)
        files = await load(conn, "reply_id", [r.id for r in page])
    return [_out(r, files.get(r.id, [])) for r in page]
