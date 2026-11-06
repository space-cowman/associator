"""Public profiles."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import text

from api.auth import CurrentUser, optional_user
from api.routes.replies import Via
from api.routes.threads import OFFSET_MAX, PAGE_DEFAULT, PAGE_MAX, Sort, ThreadOut, Window, feed
from api.routes.votes import COUNT_COLUMNS, VoteCounts, counts_from
from api.visibility import VISIBLE_TO_VIEWER

router = APIRouter(prefix="/users")

SATISFIED_POINTS = 5


class Profile(BaseModel):
    handle: str
    joined_at: datetime
    questions: int
    answers: int
    satisfied: int
    reputation: int


class ProfileAnswer(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    group: str
    thread_text: str
    text: str
    by_agent: bool
    via: Via
    created_at: datetime
    satisfied: bool
    votes: VoteCounts


@router.get("/{handle}")
async def get_profile(handle: str, request: Request) -> Profile:
    """Show a person's public profile."""
    async with request.app.state.db.connect() as conn:
        row = (
            await conn.execute(
                text(
                    """
                    SELECT u.handle, u.created_at AS joined_at,
                      (SELECT count(*) FROM threads t
                        WHERE t.author_id = u.id AND t.deleted_at IS NULL) AS questions,
                      (SELECT count(*) FROM replies r
                        JOIN threads t ON t.id = r.thread_id AND t.deleted_at IS NULL
                        WHERE r.author_id = u.id) AS answers,
                      (SELECT count(*) FROM threads t JOIN replies r ON r.id = t.satisfied_reply_id
                        WHERE r.author_id = u.id AND t.deleted_at IS NULL) AS satisfied,
                      (SELECT count(*) FROM votes v JOIN replies r ON r.id = v.reply_id
                        WHERE r.author_id = u.id AND v.voter_type = 'human' AND v.value = 1)
                      + (SELECT count(*) FROM thread_votes v JOIN threads t ON t.id = v.thread_id
                        WHERE t.author_id = u.id AND v.voter_type = 'human' AND v.value = 1)
                        AS upvotes
                    FROM users u WHERE u.handle = :h
                    """
                ),
                {"h": handle},
            )
        ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    m = row._mapping
    return Profile(
        handle=m["handle"],
        joined_at=m["joined_at"],
        questions=m["questions"],
        answers=m["answers"],
        satisfied=m["satisfied"],
        reputation=m["upvotes"] + SATISFIED_POINTS * m["satisfied"],
    )


@router.get("/{handle}/threads")
async def profile_threads(
    handle: str,
    request: Request,
    sort: Sort = "new",
    window: Window = "all",
    limit: Annotated[int, Query(ge=1, le=PAGE_MAX)] = PAGE_DEFAULT,
    before: uuid.UUID | None = None,
    offset: Annotated[int, Query(ge=0, le=OFFSET_MAX)] = 0,
    user: Annotated[CurrentUser | None, Depends(optional_user)] = None,
) -> list[ThreadOut]:
    """List a person's questions."""
    return await feed(
        request,
        "u.handle = :h",
        {"h": handle},
        sort=sort,
        window=window,
        limit=limit,
        before=before,
        offset=offset,
        viewer=user.id if user else None,
    )


@router.get("/{handle}/answers")
async def profile_answers(
    handle: str,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=PAGE_MAX)] = PAGE_DEFAULT,
    offset: Annotated[int, Query(ge=0, le=OFFSET_MAX)] = 0,
    user: Annotated[CurrentUser | None, Depends(optional_user)] = None,
) -> list[ProfileAnswer]:
    """List a person's answers."""
    async with request.app.state.db.connect() as conn:
        rows = await conn.execute(
            text(
                f"""
                SELECT r.id, r.thread_id, g.slug AS "group", t.text AS thread_text, r.text,
                       r.mode <> 'self' AS by_agent,
                       CASE r.mode WHEN 'self' THEN 'person' WHEN 'mcp' THEN 'agent'
                         ELSE 'assisted' END AS via,
                       r.created_at,
                       t.satisfied_reply_id = r.id AS satisfied,
                       v.human_up, v.human_down, v.agent_up, v.agent_down
                FROM replies r
                JOIN users u ON u.id = r.author_id
                JOIN threads t ON t.id = r.thread_id AND t.deleted_at IS NULL
                JOIN topic_groups g ON g.id = t.group_id
                CROSS JOIN LATERAL (SELECT {COUNT_COLUMNS} FROM votes WHERE reply_id = r.id) v
                WHERE u.handle = :h AND {VISIBLE_TO_VIEWER}
                ORDER BY r.created_at DESC LIMIT :limit OFFSET :offset
                """  # noqa: S608
            ),
            {
                "h": handle,
                "limit": limit,
                "offset": offset,
                "viewer": user.id if user else None,
            },
        )
    out: list[ProfileAnswer] = []
    for r in rows:
        m = dict(r._mapping)
        votes = counts_from(m)
        for k in ("human_up", "human_down", "agent_up", "agent_down"):
            m.pop(k)
        m["satisfied"] = bool(m["satisfied"])
        out.append(ProfileAnswer(**m, votes=votes))
    return out
