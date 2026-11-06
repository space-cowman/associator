"""The signed-in person's memory: view, import, edit, delete (humans only; never logged)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints
from sqlalchemy import text

from api import memory, ratelimit, safety_client
from api.auth import CurrentUser, current_user
from api.validation import safe_multiline

router = APIRouter(prefix="/me/memory")

WRITE_LIMIT = 30
WRITE_WINDOW_SECONDS = 3600
_FULL = f"Memory holds up to {memory.MAX_ITEMS} items; delete some first"


class ImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=memory.IMPORT_CHARS),
        AfterValidator(safe_multiline),
    ]


class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=memory.ITEM_CHARS),
        AfterValidator(safe_multiline),
    ]


class ItemOut(BaseModel):
    id: uuid.UUID
    text: str
    searchable: bool
    created_at: datetime
    updated_at: datetime


def _out(item: memory.Item) -> ItemOut:
    """Shape one memory item for the response."""
    return ItemOut(
        id=item.id,
        text=item.text,
        searchable=item.vector is not None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _human(user: CurrentUser) -> None:
    """Only the person, not an AI app, may do this."""
    if user.actor != "human":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only you can manage your memory")


async def _no_secrets(request: Request, items: list[str]) -> None:
    """Refuse memory items that contain keys or passwords."""
    try:
        await safety_client.check_file_text(request, "\n".join(items))
    except HTTPException as exc:
        if exc.status_code != status.HTTP_422_UNPROCESSABLE_CONTENT:
            raise
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"reason": "secret", "message": "This contains a key or password; remove it"},
        ) from None


async def _lock(conn: Any, user_id: uuid.UUID) -> int:
    """Serialise one person's writes; returns how many items they have."""
    await conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"memory:{user_id}"}
    )
    count: int = await conn.scalar(
        text("SELECT count(*) FROM memory_items WHERE user_id = :u"), {"u": user_id}
    )
    return count


@router.get("")
async def list_memory(
    request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> list[ItemOut]:
    """List my memory items."""
    _human(user)
    return [_out(i) for i in await memory.load(request, user.id)]


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_memory(
    body: ImportIn, request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> list[ItemOut]:
    """Split pasted text into items (one per line or sentence) and store them encrypted."""
    _human(user)
    await ratelimit.enforce(
        request, f"ratelimit:memory:{user.id}", WRITE_LIMIT, WRITE_WINDOW_SECONDS
    )
    new = memory.split(body.text)
    if len(new) > memory.MAX_ITEMS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, _FULL)
    await _no_secrets(request, new)
    vectors = await memory.embed(request, user, new)
    vec_model, vecs = vectors if vectors else (None, [None] * len(new))
    ids = [uuid.uuid4() for _ in new]
    async with request.app.state.db.begin() as conn:
        if await _lock(conn, user.id) + len(new) > memory.MAX_ITEMS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, _FULL)
        key = await memory.data_key(request, conn, user.id, create=True)
        if key is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Memory unavailable")
        for item_id, item, vector in zip(ids, new, vecs, strict=True):
            await conn.execute(
                text(
                    "INSERT INTO memory_items (id, user_id, text_ct, vec_ct, vec_model)"
                    " VALUES (:id, :u, :t, :v, :m)"
                ),
                {
                    "id": item_id,
                    "u": user.id,
                    "t": memory.seal(key, item_id, "text", item.encode()),
                    "v": memory.seal(key, item_id, "vec", memory.pack(vector)) if vector else None,
                    "m": vec_model if vector else None,
                },
            )
    added = set(ids)
    return [_out(i) for i in await memory.load(request, user.id) if i.id in added]


@router.patch("/{item_id}")
async def edit_memory(
    item_id: uuid.UUID,
    body: ItemIn,
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
) -> ItemOut:
    """Change one memory item."""
    _human(user)
    await ratelimit.enforce(
        request, f"ratelimit:memory:{user.id}", WRITE_LIMIT, WRITE_WINDOW_SECONDS
    )
    await _no_secrets(request, [body.text])
    vectors = await memory.embed(request, user, [body.text])
    vector = vectors[1][0] if vectors else None
    async with request.app.state.db.begin() as conn:
        await _lock(conn, user.id)
        key = await memory.data_key(request, conn, user.id, create=False)
        changed = 0
        if key is not None:
            done = await conn.execute(
                text(
                    "UPDATE memory_items SET text_ct = :t, vec_ct = :v, vec_model = :m,"
                    " updated_at = now() WHERE id = :id AND user_id = :u"
                ),
                {
                    "id": item_id,
                    "u": user.id,
                    "t": memory.seal(key, item_id, "text", body.text.encode()),
                    "v": memory.seal(key, item_id, "vec", memory.pack(vector)) if vector else None,
                    "m": vectors[0] if vectors and vector else None,
                },
            )
            changed = done.rowcount
    if changed == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memory item not found")
    found = [i for i in await memory.load(request, user.id) if i.id == item_id]
    return _out(found[0])


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory_item(
    item_id: uuid.UUID, request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> None:
    """Delete one memory item."""
    _human(user)
    async with request.app.state.db.begin() as conn:
        deleted = await conn.execute(
            text("DELETE FROM memory_items WHERE id = :id AND user_id = :u"),
            {"id": item_id, "u": user.id},
        )
    if deleted.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memory item not found")


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_memory(
    request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> None:
    """Everything."""
    _human(user)
    async with request.app.state.db.begin() as conn:
        await conn.execute(text("DELETE FROM memory_items WHERE user_id = :u"), {"u": user.id})
