"""Memory for Ask my AI: what a person's AI knows about them (PRODUCT-SPEC §9)."""

import base64
import math
import os
import re
import struct
import textwrap
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text

from api.auth import CurrentUser
from api.config import get_settings

MAX_ITEMS = 100
ITEM_CHARS = 300
IMPORT_CHARS = 4000
PURPOSE = "memory"
EMBED_PROVIDERS = ("openai", "gemini", "openrouter")
MIN_SIMILARITY = 0.2
_WORD = re.compile(r"[\w']{3,}")
_STOP = frozenset("the and for with you your are was have has this that from not but".split())


@dataclass(frozen=True)
class Item:
    id: uuid.UUID
    text: str
    vector: list[float] | None
    vec_model: str | None
    created_at: datetime
    updated_at: datetime


def split(pasted: str) -> list[str]:
    """One item per line; long lines split at sentence ends, then at words (never mid-word)."""
    items: list[str] = []
    for raw in pasted.splitlines():
        line = raw.strip().lstrip("-*•· ").strip()
        sentences = re.split(r"(?<=[.!?])\s+", line) if len(line) > ITEM_CHARS else [line]
        for sentence in sentences:
            items += textwrap.wrap(sentence, ITEM_CHARS) if sentence else []
    return list(dict.fromkeys(items))


def _ctx(user_id: uuid.UUID) -> dict[str, str]:
    """The KMS encryption context for a person's memory key."""
    return {"purpose": PURPOSE, "user_id": str(user_id)}


async def data_key(
    request: Request, conn: Any, user_id: uuid.UUID, *, create: bool
) -> bytes | None:
    """The person's 256-bit memory key, in plaintext for this request only (one KMS call)."""
    arn = get_settings().user_keys_kms_arn
    if arn is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Memory unavailable")
    kms = request.app.state.kms
    find = text("SELECT key_ciphertext FROM memory_keys WHERE user_id = :u")
    blob = await conn.scalar(find, {"u": user_id})
    if blob is None:
        if not create:
            return None
        made = await run_in_threadpool(
            kms.generate_data_key, KeyId=arn, KeySpec="AES_256", EncryptionContext=_ctx(user_id)
        )
        await conn.execute(
            text(
                "INSERT INTO memory_keys (user_id, key_ciphertext) VALUES (:u, :k)"
                " ON CONFLICT (user_id) DO NOTHING"
            ),
            {"u": user_id, "k": bytes(made["CiphertextBlob"])},
        )
        blob = await conn.scalar(find, {"u": user_id})
    out = await run_in_threadpool(
        kms.decrypt, CiphertextBlob=bytes(blob), KeyId=arn, EncryptionContext=_ctx(user_id)
    )
    return bytes(out["Plaintext"])


def seal(key: bytes, item_id: uuid.UUID, part: str, data: bytes) -> bytes:
    """AES-GCM; the item id and part are bound in, so a ciphertext moved to another row fails."""
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, data, f"{item_id}:{part}".encode())


def unseal(key: bytes, item_id: uuid.UUID, part: str, blob: bytes) -> bytes:
    """Decrypt one part of a memory item."""
    return AESGCM(key).decrypt(blob[:12], blob[12:], f"{item_id}:{part}".encode())


def pack(vector: list[float]) -> bytes:
    """Turn a vector into bytes."""
    return struct.pack(f"<{len(vector)}f", *vector)


def unpack(blob: bytes) -> list[float]:
    """Turn bytes back into a vector."""
    return list(struct.unpack(f"<{len(blob) // 4}f", blob))


async def embed(
    request: Request, user: CurrentUser, texts: list[str]
) -> tuple[str, list[list[float]]] | None:
    """None when the person has no provider with embeddings, or it fails: keywords then."""
    async with request.app.state.db.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT id, provider, model_name, key_ciphertext FROM model_registry"
                    " WHERE user_id = :u AND enabled AND provider = ANY(:p)"
                    " ORDER BY created_at LIMIT 1"
                ),
                {"u": user.id, "p": list(EMBED_PROVIDERS)},
            )
        ).one_or_none()
    if row is None:
        return None
    try:
        response = await request.app.state.gateway.post(
            "/embed",
            json={
                "request_id": uuid.uuid4().hex,
                "user_id": str(user.id),
                "texts": texts,
                "user_model": {
                    "model_id": str(row.id),
                    "provider": row.provider,
                    "model": row.model_name,
                    "key_ciphertext": base64.b64encode(bytes(row.key_ciphertext)).decode(),
                },
            },
        )
        response.raise_for_status()
        out = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    return str(out["model"]), out["vectors"]


async def load(request: Request, user_id: uuid.UUID) -> list[Item]:
    """Load and decrypt a person's memory items."""
    async with request.app.state.db.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id, text_ct, vec_ct, vec_model, created_at, updated_at"
                    " FROM memory_items WHERE user_id = :u ORDER BY created_at"
                ),
                {"u": user_id},
            )
        ).all()
        key = await data_key(request, conn, user_id, create=False) if rows else None
    if key is None:
        return []
    return [
        Item(
            id=r.id,
            text=unseal(key, r.id, "text", bytes(r.text_ct)).decode(),
            vector=unpack(unseal(key, r.id, "vec", bytes(r.vec_ct))) if r.vec_ct else None,
            vec_model=r.vec_model,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


def words(value: str) -> set[str]:
    """The lowercase words of a text, for keyword search."""
    return {w for w in _WORD.findall(value.lower()) if w not in _STOP}


def cosine(a: list[float], b: list[float]) -> float:
    """How similar two vectors are."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / ((math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))) or 1)


def rank(
    items: list[Item], query: str, query_vector: tuple[str, list[float]] | None, k: int
) -> list[Item]:
    """Order memory items by how well they match a question."""
    if query_vector is not None:
        model, q = query_vector
        scored = [(cosine(q, i.vector), i) for i in items if i.vector and i.vec_model == model]
        if scored:
            best = sorted(scored, key=lambda p: -p[0])[:k]
            return [i for s, i in best if s > MIN_SIMILARITY]
    asked = words(query)
    best_words = sorted(((len(asked & words(i.text)), i) for i in items), key=lambda p: -p[0])[:k]
    return [i for s, i in best_words if s > 0]


async def retrieve(request: Request, user: CurrentUser, query: str, k: int = 5) -> list[Item]:
    """The k items most related to the question (used only when the memory toggle is on)."""
    items = await load(request, user.id)
    if not items:
        return []
    found = await embed(request, user, [query]) if any(i.vector for i in items) else None
    return rank(items, query, (found[0], found[1][0]) if found else None, k)
