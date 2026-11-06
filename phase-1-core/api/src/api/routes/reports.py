"""Reports: messages in private chats and public questions and replies."""

import json
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api import chat_store, metrics, ratelimit
from api.auth import CurrentUser, current_user
from api.routes.conversations import active_member, human
from api.visibility import ensure_visible

router = APIRouter()
Me = Annotated[CurrentUser, Depends(current_user)]

HandleText = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{3,30}$")]


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Literal[
        "spam", "harassment", "hate", "sexual", "violence", "self_harm", "illegal", "other"
    ]
    details: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""
    message_ids: list[int] = Field(min_length=1, max_length=20)


@router.post("/conversations/{conversation_id}/reports", status_code=status.HTTP_201_CREATED)
async def report(
    conversation_id: uuid.UUID, body: ReportIn, request: Request, user: Me
) -> dict[str, str]:
    """Report messages in a private chat."""
    human(user)
    await ratelimit.enforce(request, f"ratelimit:reports:{user.id}", 10, 3600)
    report_id = uuid.uuid4()
    async with request.app.state.db.begin() as conn:
        await active_member(conn, conversation_id, user.id)
        chosen = await chat_store.read(
            request, conn, conversation_id, user.id, ids=sorted(set(body.message_ids))
        )
        if not chosen:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Tick the messages to report"
            )
        others = {m.sender for m in chosen if not m.mine and m.kind == "text"}
        snapshot = [
            {
                "sender": m.sender or "deleted-user",
                "text": m.text or "",
                "at": m.created_at.isoformat(),
                "file": m.file.filename if m.file else None,
                "kind": m.kind,
            }
            for m in chosen
        ]
        await conn.execute(
            text(
                "INSERT INTO reports"
                " (id, reporter_id, conversation_id, reported_handle, reason, details, content)"
                " VALUES (:id, :me, :c, :who, :why, :details, CAST(:content AS jsonb))"
            ),
            {
                "id": report_id,
                "me": user.id,
                "c": conversation_id,
                "who": next(iter(others)) if len(others) == 1 else None,
                "why": body.reason,
                "details": body.details or None,
                "content": json.dumps(snapshot),
            },
        )
    metrics.chat_event("report")
    metrics.report_received("private_chat")
    return {"id": str(report_id)}


Reason = Literal[
    "spam", "harassment", "hate", "sexual", "violence", "self_harm", "illegal", "other"
]


class PublicReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Reason
    details: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""


async def _report_post(
    request: Request,
    user: CurrentUser,
    body: PublicReportIn,
    *,
    thread_id: uuid.UUID | None,
    reply_id: uuid.UUID | None,
) -> dict[str, str]:
    """Report a public question or reply."""
    human(user)
    await ratelimit.enforce(request, f"ratelimit:reports:{user.id}", 10, 3600)
    report_id = uuid.uuid4()
    async with request.app.state.db.begin() as conn:
        await ensure_visible(conn, user.id, thread_id=thread_id, reply_id=reply_id)
        if reply_id is not None:
            post = (
                await conn.execute(
                    text(
                        "SELECT r.thread_id, r.author_id, u.handle, r.text, r.created_at,"
                        " r.mode <> 'self' AS by_agent"
                        " FROM replies r LEFT JOIN users u ON u.id = r.author_id WHERE r.id = :id"
                    ),
                    {"id": reply_id},
                )
            ).one()
        else:
            post = (
                await conn.execute(
                    text(
                        "SELECT t.id AS thread_id, t.author_id, u.handle, t.text, t.created_at,"
                        " t.by_agent"
                        " FROM threads t LEFT JOIN users u ON u.id = t.author_id"
                        " WHERE t.id = :id AND t.deleted_at IS NULL"
                    ),
                    {"id": thread_id},
                )
            ).one_or_none()
            if post is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        if post.author_id == user.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "You can delete your own post instead")
        snapshot = [
            {
                "sender": post.handle or "deleted-user",
                "text": post.text,
                "at": post.created_at.isoformat(),
                "by_agent": post.by_agent,
            }
        ]
        try:
            await conn.execute(
                text(
                    "INSERT INTO reports (id, reporter_id, thread_id, reply_id, reported_handle,"
                    " reason, details, content)"
                    " VALUES (:id, :me, :t, :r, :who, :why, :details, CAST(:content AS jsonb))"
                ),
                {
                    "id": report_id,
                    "me": user.id,
                    "t": post.thread_id,
                    "r": reply_id,
                    "who": post.handle,
                    "why": body.reason,
                    "details": body.details or None,
                    "content": json.dumps(snapshot),
                },
            )
        except IntegrityError:
            raise HTTPException(status.HTTP_409_CONFLICT, "You already reported this") from None
    metrics.report_received("reply" if reply_id else "question")
    return {"id": str(report_id)}


@router.post("/threads/{thread_id}/report", status_code=status.HTTP_201_CREATED)
async def report_question(
    thread_id: uuid.UUID, body: PublicReportIn, request: Request, user: Me
) -> dict[str, str]:
    """Report a public question."""
    return await _report_post(request, user, body, thread_id=thread_id, reply_id=None)


@router.post("/replies/{reply_id}/report", status_code=status.HTTP_201_CREATED)
async def report_reply(
    reply_id: uuid.UUID, body: PublicReportIn, request: Request, user: Me
) -> dict[str, str]:
    """Report a public reply."""
    return await _report_post(request, user, body, thread_id=None, reply_id=reply_id)
