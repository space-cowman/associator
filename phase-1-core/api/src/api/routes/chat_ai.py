"""AI in private chats: @platform-ai or the member's own model."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import text

from api import chat_events, chat_store, llm_client, metrics, prompts, ratelimit
from api.auth import CurrentUser, current_user
from api.chat_store import MessageOut
from api.routes.conversations import active_member, human

router = APIRouter()
Me = Annotated[CurrentUser, Depends(current_user)]

ASK_LIMIT, ASK_WINDOW = 30, 3600
MAX_CONTEXT_CHARS = 16_000
MAX_ANSWER = 4000
MAX_TOKENS = 800


class AskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: Literal["platform", "mine"]
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
    message_ids: list[int] = Field(default_factory=list, max_length=30)


class AskOut(BaseModel):
    question: MessageOut
    answer: MessageOut


@router.post("/conversations/{conversation_id}/ai")
async def ask(conversation_id: uuid.UUID, body: AskIn, request: Request, user: Me) -> AskOut:
    """Ask an AI in a chat and post its answer."""
    human(user)
    async with request.app.state.db.connect() as conn:
        await active_member(conn, conversation_id, user.id)
        settings = (
            await conn.execute(
                text("SELECT ai_enabled, ai_sharing FROM conversations WHERE id = :c"),
                {"c": conversation_id},
            )
        ).one()
        if not settings.ai_enabled:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "An admin switched AI off for this chat")
        rows = await conn.execute(
            text(
                "SELECT u.handle FROM conversation_members m JOIN users u ON u.id = m.user_id"
                " WHERE m.conversation_id = :c AND m.state IN ('invited', 'active')"
            ),
            {"c": conversation_id},
        )
        handles = [r.handle for r in rows]
        shared = [
            m
            for m in await chat_store.read(
                request, conn, conversation_id, user.id, ids=sorted(set(body.message_ids))
            )
            if m.text
        ]
    context = [(m.sender or "deleted-user", m.text or "") for m in shared]
    if sum(len(t) for _, t in context) + len(body.question) > MAX_CONTEXT_CHARS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Too much text: tick fewer messages"
        )
    await ratelimit.enforce(request, f"ratelimit:chat-ai:{user.id}", ASK_LIMIT, ASK_WINDOW)
    answer = await llm_client.complete(
        request,
        user,
        own_model=body.model == "mine",
        system=prompts.CHAT_SYSTEM,
        messages=prompts.chat_messages(context, body.question),
        max_tokens=MAX_TOKENS,
        privacy="private",
        names=handles,
        trace="chat_ai" if settings.ai_sharing else "off",
        trace_shared=settings.ai_sharing,
        trace_messages=prompts.chat_messages([], body.question) if settings.ai_sharing else None,
    )
    reply = prompts.clean_output(answer.text)
    if not reply:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "The model gave no answer. Try again."
        )
    label = "Platform AI" if body.model == "platform" else answer.model
    async with request.app.state.db.begin() as conn:
        await active_member(conn, conversation_id, user.id)
        q_id = await chat_store.add(
            request,
            conn,
            conversation_id,
            user.id,
            "ask",
            body.question,
            meta={"model": label, "shared": [m.id for m in shared]},
        )
        a_id = await chat_store.add(
            request,
            conn,
            conversation_id,
            user.id,
            "ai",
            reply[:MAX_ANSWER],
            meta={"model": label, "asked_by": user.handle},
        )
        q, a = await chat_store.read(request, conn, conversation_id, user.id, ids=[q_id, a_id])
        members = await chat_events.member_ids(conn, conversation_id, include_invited=False)
    await chat_events.publish(request.app.state.redis, members, conversation_id, "message")
    metrics.chat_event("ai_answer")
    return AskOut(question=q, answer=a)
