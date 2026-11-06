"""Private chat messages (server-stored since 2026-11-05) and the live WebSocket."""

import asyncio
import contextlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, status
from fastapi.concurrency import run_in_threadpool
from fastapi.websockets import WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator
from sqlalchemy import text

from api import chat_events, chat_store, files, metrics, ratelimit
from api.auth import CurrentUser, current_user, verify_token
from api.chat_store import MessageOut
from api.routes.conversations import active_member, human
from api.routes.uploads import LINK_SECONDS, _bucket

log = logging.getLogger("api.chat")
router = APIRouter()
Me = Annotated[CurrentUser, Depends(current_user)]

SEND_LIMIT, SEND_WINDOW = 300, 600
SOCKETS_PER_PERSON = 10
PING_EVERY = 25
_open: dict[uuid.UUID, int] = {}


class SendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: Annotated[str, StringConstraints(max_length=chat_store.MAX_TEXT)] = ""
    attachment_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def something(self) -> "SendIn":
        """A message needs text or a file."""
        if not self.text.strip() and self.attachment_id is None:
            raise ValueError("Write a message or attach a file")
        return self


@router.post("/conversations/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
async def send(conversation_id: uuid.UUID, body: SendIn, request: Request, user: Me) -> MessageOut:
    """Send a message to a chat."""
    human(user)
    await ratelimit.enforce(request, f"ratelimit:chat:send:{user.id}", SEND_LIMIT, SEND_WINDOW)
    async with request.app.state.db.begin() as conn:
        await active_member(conn, conversation_id, user.id)
        if body.attachment_id is not None:
            tied = await conn.execute(
                text(
                    "UPDATE attachments SET conversation_id = :c WHERE id = :a AND owner_id = :u"
                    " AND status = 'ready' AND conversation_id IS NULL"
                    " AND thread_id IS NULL AND reply_id IS NULL"
                ),
                {"c": conversation_id, "a": body.attachment_id, "u": user.id},
            )
            if tied.rowcount != 1:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "File not found")
        message_id = await chat_store.add(
            request,
            conn,
            conversation_id,
            user.id,
            "text",
            body.text.strip() or None,
            attachment_id=body.attachment_id,
        )
        (message,) = await chat_store.read(
            request, conn, conversation_id, user.id, ids=[message_id]
        )
        members = await chat_events.member_ids(conn, conversation_id, include_invited=False)
    await chat_events.publish(request.app.state.redis, members, conversation_id, "message")
    metrics.chat_event("message")
    return message


@router.get("/conversations/{conversation_id}/messages")
async def messages(
    conversation_id: uuid.UUID,
    request: Request,
    user: Me,
    after: Annotated[int, Query(ge=0)] = 0,
    before: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[MessageOut]:
    """New messages after `after`; without it the newest page (older ones with `before`)."""
    human(user)
    async with request.app.state.db.connect() as conn:
        await active_member(conn, conversation_id, user.id)
        return await chat_store.read(
            request, conn, conversation_id, user.id, after=after, before=before, limit=limit
        )


@router.get("/conversations/{conversation_id}/files/{attachment_id}")
async def chat_file(
    conversation_id: uuid.UUID, attachment_id: uuid.UUID, request: Request, user: Me
) -> dict[str, str]:
    """A short-lived link to a file sent in the chat, for members only."""
    human(user)
    async with request.app.state.db.connect() as conn:
        await active_member(conn, conversation_id, user.id)
        row = (
            await conn.execute(
                text(
                    "SELECT content_type, filename FROM attachments"
                    " WHERE id = :a AND conversation_id = :c AND status = 'ready'"
                ),
                {"a": attachment_id, "c": conversation_id},
            )
        ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    inline = files.TYPES[row.content_type].inline
    url: str = await run_in_threadpool(
        request.app.state.s3.generate_presigned_url,
        "get_object",
        Params={
            "Bucket": _bucket(),
            "Key": f"files/{attachment_id}",
            "ResponseContentType": row.content_type,
            "ResponseContentDisposition": "inline"
            if inline
            else f'attachment; filename="{row.filename}"',
        },
        ExpiresIn=LINK_SECONDS,
    )
    return {"url": url}


@router.websocket("/chat/ws")
async def socket(ws: WebSocket) -> None:
    """Live notices for the signed-in person."""
    await ws.accept()
    user: CurrentUser | None = None
    try:
        first = await asyncio.wait_for(ws.receive_text(), timeout=10)
        token = json.loads(first).get("token", "")
        user = verify_token(token)
        expires = jwt.decode(token, options={"verify_signature": False})["exp"]
    except (TimeoutError, ValueError, KeyError, AttributeError, jwt.InvalidTokenError):
        await ws.close(code=4401, reason="Not authenticated")
        return
    except WebSocketDisconnect:
        return
    if user.actor != "human":
        await ws.close(code=4403, reason="Private chats are for people")
        return
    if _open.get(user.id, 0) >= SOCKETS_PER_PERSON:
        await ws.close(code=4429, reason="Too many open tabs")
        return
    _open[user.id] = _open.get(user.id, 0) + 1
    metrics.socket_opened()
    pubsub = ws.app.state.redis.pubsub()
    try:
        await pubsub.subscribe(chat_events.channel(user.id))
        await ws.send_text(json.dumps({"type": "ready"}))
        reader = asyncio.create_task(_until_closed(ws))
        last_sent = datetime.now(UTC).timestamp()
        while not reader.done():
            now = datetime.now(UTC).timestamp()
            if now >= expires:
                await ws.close(code=4401, reason="Token expired")
                break
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg is not None:
                await ws.send_text(msg["data"])
                last_sent = now
            elif now - last_sent > PING_EVERY:
                await ws.send_text('{"type":"ping"}')
                last_sent = now
        reader.cancel()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        metrics.socket_closed()
        _open[user.id] -= 1
        if _open[user.id] <= 0:
            _open.pop(user.id, None)
        with contextlib.suppress(Exception):
            await pubsub.aclose()


async def _until_closed(ws: WebSocket) -> None:
    """The page sends nothing after the token; this only notices when it goes away."""
    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        while True:
            await ws.receive_text()
