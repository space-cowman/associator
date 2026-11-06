"""Live notices for private chats, over Redis pub/sub: "something changed in conversation X"."""

import json
import logging
import uuid
from typing import Literal

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

log = logging.getLogger("api.chat")

Kind = Literal["message", "members"]


def channel(user_id: uuid.UUID) -> str:
    """The live-notice channel name for one person."""
    return f"chat:user:{user_id}"


async def member_ids(
    conn: AsyncConnection, conversation_id: uuid.UUID, *, include_invited: bool = True
) -> list[uuid.UUID]:
    """The ids of the people in a chat."""
    states = ("invited", "active") if include_invited else ("active",)
    rows = await conn.execute(
        text(
            "SELECT user_id FROM conversation_members"
            " WHERE conversation_id = :c AND state = ANY(:s)"
        ),
        {"c": conversation_id, "s": list(states)},
    )
    return [r.user_id for r in rows]


async def publish(
    redis: Redis, user_ids: list[uuid.UUID], conversation_id: uuid.UUID, kind: Kind
) -> None:
    """Best effort: a missed notice is caught up on the next sync, so failures are only logged."""
    notice = json.dumps({"type": kind, "conversation_id": str(conversation_id)})
    try:
        async with redis.pipeline(transaction=False) as pipe:
            for uid in set(user_ids):
                pipe.publish(channel(uid), notice)
            await pipe.execute()
    except Exception:  # noqa: BLE001
        log.warning("chat notice not published", extra={"conversation_id": str(conversation_id)})
