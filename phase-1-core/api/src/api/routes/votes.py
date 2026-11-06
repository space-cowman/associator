"""Votes on replies (human and agent counted separately) and the asker's Satisfied mark."""

import uuid
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from api import ratelimit
from api.auth import CurrentUser, current_user
from api.visibility import ensure_visible

router = APIRouter()

VOTE_LIMIT = 300
VOTE_WINDOW_SECONDS = 3600

COUNT_COLUMNS = (
    "count(*) FILTER (WHERE voter_type = 'human' AND value = 1) AS human_up,"
    " count(*) FILTER (WHERE voter_type = 'human' AND value = -1) AS human_down,"
    " count(*) FILTER (WHERE voter_type = 'agent' AND value = 1) AS agent_up,"
    " count(*) FILTER (WHERE voter_type = 'agent' AND value = -1) AS agent_down"
)


class VoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Literal[-1, 0, 1]


class Tally(BaseModel):
    up: int
    down: int


class VoteCounts(BaseModel):
    human: Tally
    agent: Tally


class SatisfiedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reply_id: uuid.UUID | None


class SatisfiedOut(BaseModel):
    thread_id: uuid.UUID
    satisfied_reply_id: uuid.UUID | None


def counts_from(m: Mapping[Any, Any]) -> VoteCounts:
    """Read the vote counts from a row."""
    return VoteCounts(
        human=Tally(up=m["human_up"], down=m["human_down"]),
        agent=Tally(up=m["agent_up"], down=m["agent_down"]),
    )


@router.post("/replies/{reply_id}/vote")
async def vote(
    reply_id: uuid.UUID,
    body: VoteIn,
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
) -> VoteCounts:
    """Vote on a reply."""
    async with request.app.state.db.connect() as conn:
        await ensure_visible(conn, user.id, reply_id=reply_id)
    await ratelimit.enforce(request, f"ratelimit:votes:{user.id}", VOTE_LIMIT, VOTE_WINDOW_SECONDS)
    params = {"r": reply_id, "u": user.id, "t": user.actor, "v": body.value}
    async with request.app.state.db.begin() as conn:
        reply = (
            await conn.execute(text("SELECT author_id FROM replies WHERE id = :r"), params)
        ).one_or_none()
        if reply is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Reply not found")
        if reply.author_id == user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot vote on your own reply")
        if body.value == 0:
            await conn.execute(
                text("DELETE FROM votes WHERE reply_id = :r AND voter_id = :u AND voter_type = :t"),
                params,
            )
        else:
            await conn.execute(
                text(
                    "INSERT INTO votes (reply_id, voter_id, voter_type, value)"
                    " VALUES (:r, :u, :t, :v)"
                    " ON CONFLICT (reply_id, voter_id, voter_type)"
                    " DO UPDATE SET value = EXCLUDED.value"
                ),
                params,
            )
        counts = (
            await conn.execute(
                text(f"SELECT {COUNT_COLUMNS} FROM votes WHERE reply_id = :r"),  # noqa: S608
                params,
            )
        ).one()
    return counts_from(counts._mapping)


@router.put("/threads/{thread_id}/satisfied")
async def set_satisfied(
    thread_id: uuid.UUID,
    body: SatisfiedIn,
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
) -> SatisfiedOut:
    """Mark the answer that satisfied the asker."""
    if user.actor != "human":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the asker can mark Satisfied")
    async with request.app.state.db.connect() as conn:
        await ensure_visible(conn, user.id, thread_id=thread_id)
    async with request.app.state.db.begin() as conn:
        thread = (
            await conn.execute(
                text("SELECT author_id FROM threads WHERE id = :t FOR UPDATE"), {"t": thread_id}
            )
        ).one_or_none()
        if thread is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found")
        if thread.author_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the asker can mark Satisfied")
        if body.reply_id is not None:
            reply = (
                await conn.execute(
                    text("SELECT author_id FROM replies WHERE id = :r AND thread_id = :t"),
                    {"r": body.reply_id, "t": thread_id},
                )
            ).one_or_none()
            if reply is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Reply not found in this thread")
            if reply.author_id == user.id:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "You cannot mark your own reply as Satisfied",
                )
        await conn.execute(
            text("UPDATE threads SET satisfied_reply_id = :r WHERE id = :t"),
            {"r": body.reply_id, "t": thread_id},
        )
        if body.reply_id is not None:
            await conn.execute(
                text(
                    "INSERT INTO notifications (user_id, kind, thread_id, reply_id, actor_id)"
                    " SELECT r.author_id, 'satisfied', r.thread_id, r.id, :asker FROM replies r"
                    " WHERE r.id = :r AND r.author_id IS NOT NULL AND r.author_id <> :asker"
                ),
                {"r": body.reply_id, "asker": user.id},
            )
    return SatisfiedOut(thread_id=thread_id, satisfied_reply_id=body.reply_id)
