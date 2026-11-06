"""Your notifications."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy import text

from api.auth import CurrentUser, current_user
from api.routes.replies import Via

router = APIRouter(prefix="/me/notifications")


class Notification(BaseModel):
    id: uuid.UUID
    kind: Literal["reply", "satisfied"]
    thread_id: uuid.UUID
    thread_text: str
    reply_id: uuid.UUID | None
    actor: str | None
    by_agent: bool
    via: Via | None
    created_at: datetime
    read: bool


class Notifications(BaseModel):
    unread: int
    items: list[Notification]


@router.get("")
async def my_notifications(
    request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> Notifications:
    """List my notifications."""
    async with request.app.state.db.connect() as conn:
        unread = await conn.scalar(
            text("SELECT count(*) FROM notifications WHERE user_id = :u AND read_at IS NULL"),
            {"u": user.id},
        )
        rows = await conn.execute(
            text(
                "SELECT n.id, n.kind, n.thread_id, left(t.text, 140) AS thread_text, n.reply_id,"
                " a.handle AS actor, coalesce(r.mode <> 'self', false) AS by_agent,"
                " CASE r.mode WHEN 'self' THEN 'person' WHEN 'mcp' THEN 'agent'"
                " WHEN 'ask_my_ai' THEN 'assisted' WHEN 'platform_ai' THEN 'assisted' END AS via,"
                " n.created_at, n.read_at IS NOT NULL AS read"
                " FROM notifications n"
                " JOIN threads t ON t.id = n.thread_id AND t.deleted_at IS NULL"
                " LEFT JOIN replies r ON r.id = n.reply_id"
                " LEFT JOIN users a ON a.id = n.actor_id"
                " WHERE n.user_id = :u ORDER BY n.created_at DESC LIMIT 30"
            ),
            {"u": user.id},
        )
    return Notifications(unread=unread or 0, items=[Notification(**r._mapping) for r in rows])


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(
    request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> None:
    """Mark all my notifications as read."""
    async with request.app.state.db.begin() as conn:
        await conn.execute(
            text("UPDATE notifications SET read_at = now() WHERE user_id = :u AND read_at IS NULL"),
            {"u": user.id},
        )
