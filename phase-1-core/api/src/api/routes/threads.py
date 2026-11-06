"""Questions: post, read, list, vote, delete and find similar."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from psycopg.errors import QueryCanceled
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import Row, text
from sqlalchemy.exc import DBAPIError

from api import formatting, ratelimit, safety_client
from api.attachments import AttachmentIds, AttachmentOut, link, load
from api.auth import CurrentUser, current_user, optional_user
from api.routes.votes import (
    COUNT_COLUMNS,
    VOTE_LIMIT,
    VOTE_WINDOW_SECONDS,
    VoteCounts,
    VoteIn,
    counts_from,
)
from api.similar import find_similar
from api.validation import safe_multiline
from api.visibility import VISIBLE_TO_VIEWER, ensure_visible

router = APIRouter()

CREATE_LIMIT = 20
CREATE_WINDOW_SECONDS = 3600
PAGE_DEFAULT, PAGE_MAX = 20, 50

GroupSlug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{2,40}$")]
PostText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    AfterValidator(safe_multiline),
]


class ThreadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group: GroupSlug
    text: PostText
    attachments: AttachmentIds = []
    confirm_personal_data: bool = False


class ThreadOut(BaseModel):
    id: uuid.UUID
    group: str
    text: str
    author: str | None
    by_agent: bool
    created_at: datetime
    satisfied_reply_id: uuid.UUID | None
    reply_count: int
    votes: VoteCounts
    warnings: list[str]
    attachments: list[AttachmentOut]


ThreadDetail = ThreadOut


class SimilarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: PostText
    limit: int = Field(default=5, ge=1, le=10)


class SimilarOut(BaseModel):
    id: uuid.UUID
    group: str
    text: str
    answered: bool


_SELECT = f"""
    SELECT t.id, g.slug AS group_slug, t.text, u.handle AS author, t.by_agent,
           t.created_at, t.satisfied_reply_id, t.warnings,
           rc.reply_count,
           v.human_up, v.human_down, v.agent_up, v.agent_down
    FROM threads t
    JOIN topic_groups g ON g.id = t.group_id
    LEFT JOIN users u ON u.id = t.author_id
    CROSS JOIN LATERAL (SELECT {COUNT_COLUMNS} FROM thread_votes WHERE thread_id = t.id) v
    CROSS JOIN LATERAL (SELECT count(*) AS reply_count FROM replies WHERE thread_id = t.id) rc
"""  # noqa: S608


def _out(row: Row[Any], files: list[AttachmentOut]) -> ThreadOut:
    """Shape one question for the response."""
    m = row._mapping
    return ThreadOut(
        id=m["id"],
        group=m["group_slug"],
        text=m["text"],
        author=m["author"],
        by_agent=m["by_agent"],
        created_at=m["created_at"],
        satisfied_reply_id=m["satisfied_reply_id"],
        reply_count=m["reply_count"],
        votes=counts_from(m),
        warnings=m["warnings"],
        attachments=files,
    )


@router.post("/threads", status_code=status.HTTP_201_CREATED)
async def create_thread(
    body: ThreadIn, request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> ThreadDetail:
    """Post a question."""
    await ratelimit.enforce(
        request, f"ratelimit:threads:create:{user.id}", CREATE_LIMIT, CREATE_WINDOW_SECONDS
    )
    warnings = await safety_client.check(
        request,
        body.text,
        formatting.for_safety(body.text),
        personal_data="allow" if body.confirm_personal_data else "ask",
    )
    labels = formatting.warning_labels(warnings)
    async with request.app.state.db.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "INSERT INTO threads (group_id, author_id, text, by_agent, warnings)"
                    " SELECT g.id, :uid, :text, :agent, :warnings"
                    " FROM topic_groups g WHERE g.slug = :group"
                    " RETURNING id, created_at"
                ),
                {
                    "uid": user.id,
                    "text": body.text,
                    "warnings": labels,
                    "group": body.group,
                    "agent": user.actor == "agent",
                },
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")
        files = await link(conn, user.id, body.attachments, thread_id=row.id)
    return ThreadDetail(
        id=row.id,
        group=body.group,
        text=body.text,
        author=user.handle,
        by_agent=user.actor == "agent",
        created_at=row.created_at,
        satisfied_reply_id=None,
        reply_count=0,
        votes=counts_from({k: 0 for k in ("human_up", "human_down", "agent_up", "agent_down")}),
        warnings=labels,
        attachments=files,
    )


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: uuid.UUID,
    request: Request,
    user: Annotated[CurrentUser | None, Depends(optional_user)] = None,
) -> ThreadDetail:
    """Show one question."""
    async with request.app.state.db.connect() as conn:
        await ensure_visible(conn, user.id if user else None, thread_id=thread_id)
    async with request.app.state.db.connect() as conn:
        row = (
            await conn.execute(
                text(_SELECT + " WHERE t.id = :id AND t.deleted_at IS NULL"), {"id": thread_id}
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found")
        files = await load(conn, "thread_id", [thread_id])
    return _out(row, files.get(thread_id, []))


Sort = Literal["new", "top", "hot"]
Window = Literal["day", "week", "month", "all"]
WINDOWS = {"day": "1 day", "week": "7 days", "month": "30 days", "all": None}
_HOT = (
    "((v.human_up - v.human_down) + rc.reply_count * 0.5 + 1)"
    " / power(extract(epoch FROM (now() - t.created_at)) / 3600 + 2, 1.5)"
)
OFFSET_MAX = 1000
SEARCH_LIMIT = 30


async def feed(
    request: Request,
    where: str,
    params: dict[str, Any],
    *,
    sort: Sort,
    window: Window,
    limit: int,
    before: uuid.UUID | None,
    offset: int,
    viewer: uuid.UUID | None = None,
) -> list[ThreadOut]:
    """The one feed query: newest (keyset paging), top (by people's score) or hot."""
    clauses = ["t.deleted_at IS NULL", VISIBLE_TO_VIEWER, where]
    if sort == "new":
        clauses.append(
            "(CAST(:before AS uuid) IS NULL OR (t.created_at, t.id) <"
            " (SELECT created_at, id FROM threads WHERE id = CAST(:before AS uuid)))"
        )
        order = "t.created_at DESC, t.id DESC"
        paging = ""
    else:
        if sort == "top" and WINDOWS[window]:
            clauses.append(f"t.created_at > now() - interval '{WINDOWS[window]}'")
        order = (
            "(v.human_up - v.human_down) DESC, t.created_at DESC"
            if sort == "top"
            else f"{_HOT} DESC, t.created_at DESC"
        )
        paging = " OFFSET :offset"
    sql_text = (
        _SELECT  # noqa: S608
        + " WHERE "
        + " AND ".join(c for c in clauses if c)
        + f" ORDER BY {order} LIMIT :limit{paging}"
    )
    async with request.app.state.db.connect() as conn:
        rows = await conn.execute(
            text(sql_text),
            {**params, "before": before, "limit": limit, "offset": offset, "viewer": viewer},
        )
        page = list(rows)
        files = await load(conn, "thread_id", [r.id for r in page])
    return [_out(r, files.get(r.id, [])) for r in page]


@router.get("/threads")
async def list_threads(
    request: Request,
    sort: Sort = "new",
    window: Window = "all",
    limit: Annotated[int, Query(ge=1, le=PAGE_MAX)] = PAGE_DEFAULT,
    before: uuid.UUID | None = None,
    offset: Annotated[int, Query(ge=0, le=OFFSET_MAX)] = 0,
    user: Annotated[CurrentUser | None, Depends(optional_user)] = None,
) -> list[ThreadOut]:
    """The all-groups feed (home page)."""
    return await feed(
        request,
        "",
        {},
        sort=sort,
        window=window,
        limit=limit,
        before=before,
        offset=offset,
        viewer=user.id if user else None,
    )


@router.post("/threads/{thread_id}/vote")
async def vote_thread(
    thread_id: uuid.UUID,
    body: VoteIn,
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
) -> VoteCounts:
    """Vote on a question."""
    async with request.app.state.db.connect() as conn:
        await ensure_visible(conn, user.id, thread_id=thread_id)
    await ratelimit.enforce(request, f"ratelimit:votes:{user.id}", VOTE_LIMIT, VOTE_WINDOW_SECONDS)
    params = {"t": thread_id, "u": user.id, "type": user.actor, "v": body.value}
    async with request.app.state.db.begin() as conn:
        thread = (
            await conn.execute(
                text("SELECT author_id FROM threads WHERE id = :t AND deleted_at IS NULL"), params
            )
        ).one_or_none()
        if thread is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found")
        if thread.author_id == user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot vote on your own question")
        if body.value == 0:
            await conn.execute(
                text(
                    "DELETE FROM thread_votes"
                    " WHERE thread_id = :t AND voter_id = :u AND voter_type = :type"
                ),
                params,
            )
        else:
            await conn.execute(
                text(
                    "INSERT INTO thread_votes (thread_id, voter_id, voter_type, value)"
                    " VALUES (:t, :u, :type, :v)"
                    " ON CONFLICT (thread_id, voter_id, voter_type)"
                    " DO UPDATE SET value = EXCLUDED.value"
                ),
                params,
            )
        counts = (
            await conn.execute(
                text(f"SELECT {COUNT_COLUMNS} FROM thread_votes WHERE thread_id = :t"),  # noqa: S608
                params,
            )
        ).one()
    return counts_from(counts._mapping)


@router.get("/groups/{slug}/threads")
async def list_group_threads(
    slug: GroupSlug,
    request: Request,
    sort: Sort = "new",
    window: Window = "all",
    limit: Annotated[int, Query(ge=1, le=PAGE_MAX)] = PAGE_DEFAULT,
    before: uuid.UUID | None = None,
    offset: Annotated[int, Query(ge=0, le=OFFSET_MAX)] = 0,
    user: Annotated[CurrentUser | None, Depends(optional_user)] = None,
) -> list[ThreadOut]:
    """List a cluster's questions."""
    async with request.app.state.db.connect() as conn:
        await ensure_visible(conn, user.id if user else None, slug=slug)
    return await feed(
        request,
        "g.slug = :slug",
        {"slug": slug},
        sort=sort,
        window=window,
        limit=limit,
        before=before,
        offset=offset,
        viewer=user.id if user else None,
    )


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: uuid.UUID, request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> None:
    """Delete my own question."""
    if user.actor != "human":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only you can delete your questions")
    async with request.app.state.db.begin() as conn:
        deleted = await conn.execute(
            text(
                "UPDATE threads SET deleted_at = now()"
                " WHERE id = :id AND author_id = :u AND deleted_at IS NULL"
            ),
            {"id": thread_id, "u": user.id},
        )
    if deleted.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found")


@router.post("/threads/search-similar")
async def search_similar(
    body: SimilarIn,
    request: Request,
    user: Annotated[CurrentUser | None, Depends(optional_user)] = None,
) -> list[SimilarOut]:
    """POST, not GET: keeps the user's text out of URLs and access logs."""
    who = f"user:{user.id}" if user else f"ip:{request.client.host if request.client else '?'}"
    await ratelimit.enforce(request, f"ratelimit:search:{who}", SEARCH_LIMIT, 60)
    try:
        async with request.app.state.db.begin() as conn:
            await conn.execute(text("SET LOCAL statement_timeout = '2s'"))
            found = await find_similar(
                conn, body.text, limit=body.limit, viewer=user.id if user else None
            )
    except DBAPIError as exc:
        if isinstance(exc.orig, QueryCanceled):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Search is busy") from None
        raise
    return [
        SimilarOut(id=f.id, group=f.group_slug, text=f.text, answered=f.answered) for f in found
    ]
