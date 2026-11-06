"""Private chat messages, stored by the server and encrypted at rest (migration 0032)."""

import json
import os
import uuid
from datetime import datetime
from typing import Any, Literal

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from api.attachments import AttachmentOut
from api.config import get_settings

PURPOSE = "chat"
MAX_TEXT = 4000


class MessageOut(BaseModel):
    id: int
    kind: Literal["text", "ask", "ai"]
    sender: str | None
    mine: bool
    text: str | None
    file: AttachmentOut | None
    meta: dict[str, Any]
    created_at: datetime


def _ctx(conversation_id: uuid.UUID) -> dict[str, str]:
    """The KMS encryption context for a chat's key."""
    return {"purpose": PURPOSE, "conversation_id": str(conversation_id)}


async def chat_key(
    request: Request, conn: AsyncConnection, conversation_id: uuid.UUID, *, create: bool
) -> bytes | None:
    """The chat's key in plaintext, for this request only."""
    arn = get_settings().user_keys_kms_arn
    if arn is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Chats are unavailable")
    kms = request.app.state.kms
    find = text("SELECT key_ciphertext FROM conversation_keys WHERE conversation_id = :c")
    blob = await conn.scalar(find, {"c": conversation_id})
    if blob is None:
        if not create:
            return None
        made = await run_in_threadpool(
            kms.generate_data_key,
            KeyId=arn,
            KeySpec="AES_256",
            EncryptionContext=_ctx(conversation_id),
        )
        await conn.execute(
            text(
                "INSERT INTO conversation_keys (conversation_id, key_ciphertext) VALUES (:c, :k)"
                " ON CONFLICT (conversation_id) DO NOTHING"
            ),
            {"c": conversation_id, "k": bytes(made["CiphertextBlob"])},
        )
        blob = await conn.scalar(find, {"c": conversation_id})
    out = await run_in_threadpool(
        kms.decrypt,
        CiphertextBlob=bytes(blob),
        KeyId=arn,
        EncryptionContext=_ctx(conversation_id),
    )
    return bytes(out["Plaintext"])


def seal(key: bytes, message_id: int, body: str) -> bytes:
    """Encrypt a message, bound to its id."""
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, body.encode(), f"msg:{message_id}".encode())


def unseal(key: bytes, message_id: int, blob: bytes) -> str:
    """Decrypt a message sealed with its id."""
    return AESGCM(key).decrypt(blob[:12], blob[12:], f"msg:{message_id}".encode()).decode()


async def add(
    request: Request,
    conn: AsyncConnection,
    conversation_id: uuid.UUID,
    sender_id: uuid.UUID,
    kind: Literal["text", "ask", "ai"],
    body: str | None,
    *,
    attachment_id: uuid.UUID | None = None,
    meta: dict[str, Any] | None = None,
) -> int:
    """Store one message; the id is taken first so the ciphertext can be bound to it."""
    message_id = int(await conn.scalar(text("SELECT nextval('chat_messages_id_seq')")))
    sealed = None
    if body:
        key = await chat_key(request, conn, conversation_id, create=True)
        if key is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Chats are unavailable")
        sealed = seal(key, message_id, body)
    await conn.execute(
        text(
            "INSERT INTO chat_messages"
            " (id, conversation_id, sender_id, kind, body_sealed, attachment_id, meta)"
            " VALUES (:id, :c, :s, :k, :b, :a, CAST(:m AS jsonb))"
        ),
        {
            "id": message_id,
            "c": conversation_id,
            "s": sender_id,
            "k": kind,
            "b": sealed,
            "a": attachment_id,
            "m": json.dumps(meta or {}),
        },
    )
    return message_id


_SELECT = (
    "SELECT m.id, m.kind, m.sender_id, u.handle AS sender, m.body_sealed, m.meta, m.created_at,"
    " a.id AS file_id, a.kind AS file_kind, a.filename, a.content_type, a.size_bytes"
    " FROM chat_messages m"
    " LEFT JOIN users u ON u.id = m.sender_id"
    " LEFT JOIN attachments a ON a.id = m.attachment_id AND a.status = 'ready'"
    " WHERE m.conversation_id = :c"
)


async def read(
    request: Request,
    conn: AsyncConnection,
    conversation_id: uuid.UUID,
    me: uuid.UUID,
    *,
    after: int = 0,
    before: int | None = None,
    ids: list[int] | None = None,
    limit: int = 100,
) -> list[MessageOut]:
    """Messages in order: after `after`, or the latest `limit` before `before`, or by `ids`."""
    params: dict[str, Any] = {"c": conversation_id, "n": limit}
    if ids is not None:
        sql = _SELECT + " AND m.id = ANY(:ids) ORDER BY m.id"
        params["ids"] = ids
    elif after:
        sql = _SELECT + " AND m.id > :after ORDER BY m.id LIMIT :n"
        params["after"] = after
    else:
        sql = (
            f"SELECT * FROM ({_SELECT}{' AND m.id < :before' if before else ''}"  # noqa: S608
            " ORDER BY m.id DESC LIMIT :n) page ORDER BY id"
        )
        if before:
            params["before"] = before
    rows = (await conn.execute(text(sql), params)).all()
    key = None
    if any(r.body_sealed is not None for r in rows):
        key = await chat_key(request, conn, conversation_id, create=False)
    out = []
    for r in rows:
        body = unseal(key, r.id, bytes(r.body_sealed)) if key and r.body_sealed else None
        file = (
            AttachmentOut(
                id=r.file_id,
                kind=r.file_kind,
                filename=r.filename,
                content_type=r.content_type,
                size_bytes=r.size_bytes,
            )
            if r.file_id
            else None
        )
        out.append(
            MessageOut(
                id=r.id,
                kind=r.kind,
                sender=r.sender,
                mine=r.sender_id == me,
                text=body,
                file=file,
                meta=r.meta or {},
                created_at=r.created_at,
            )
        )
    return out
