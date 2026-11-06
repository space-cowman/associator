"""Private clusters and one-to-one chats: people and membership (phase 1b, step A)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from api import chat_events, metrics, ratelimit
from api.auth import CurrentUser, current_user

router = APIRouter()

MAX_PEOPLE = 50
CREATE_LIMIT, CREATE_WINDOW = 20, 3600
INVITE_LIMIT, INVITE_WINDOW = 100, 3600

Handle = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{3,30}$")]
Name = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=60, pattern=r"^[^\x00-\x1f\x7f]+$"
    ),
]
Me = Annotated[CurrentUser, Depends(current_user)]


def human(user: CurrentUser) -> None:
    """Only people, not AI apps, may use private chats."""
    if user.actor != "human":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Private chats are for people, not AI apps")


def _not_found() -> HTTPException:
    """A plain "not found" error."""
    return HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


class ClusterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    members: list[Handle] = Field(default_factory=list, max_length=MAX_PEOPLE - 1)


class DirectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    handle: Handle


class InviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    handles: list[Handle] = Field(min_length=1, max_length=MAX_PEOPLE - 1)


class ClusterPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name | None = None
    ai_enabled: bool | None = None
    ai_sharing: bool | None = None


class RoleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["admin", "member"]


class Member(BaseModel):
    handle: str
    role: Literal["admin", "member"]
    state: Literal["invited", "active"]


class ConversationOut(BaseModel):
    id: uuid.UUID
    kind: Literal["cluster", "direct"]
    title: str
    my_state: Literal["invited", "active"]
    my_role: Literal["admin", "member"]
    invited_by: str | None
    member_count: int
    ai_enabled: bool
    ai_sharing: bool
    created_at: datetime


class ConversationDetail(ConversationOut):
    members: list[Member]


class Created(BaseModel):
    conversation: ConversationOut
    not_invited: list[str]


_LIST = """
    SELECT c.id, c.kind, c.ai_enabled, c.ai_sharing, c.created_at,
           me.state AS my_state, me.role AS my_role,
           inv.handle AS invited_by,
           CASE WHEN c.kind = 'cluster' THEN c.name ELSE '@' || other.handle END AS title,
           (SELECT count(*) FROM conversation_members m
             WHERE m.conversation_id = c.id AND m.state = 'active') AS member_count
    FROM conversations c
    JOIN conversation_members me ON me.conversation_id = c.id AND me.user_id = :me
    LEFT JOIN users inv ON inv.id = me.invited_by
    LEFT JOIN users other ON c.kind = 'direct'
         AND other.id = CASE WHEN c.direct_low = :me THEN c.direct_high ELSE c.direct_low END
    WHERE me.state IN ('invited', 'active')
"""


async def _user_id(conn: AsyncConnection, handle: str) -> uuid.UUID | None:
    """Find a person's id by handle."""
    found: uuid.UUID | None = await conn.scalar(
        text("SELECT id FROM users WHERE handle = :h"), {"h": handle}
    )
    return found


async def _blocked_between(conn: AsyncConnection, a: uuid.UUID, b: uuid.UUID) -> bool:
    """Whether either person blocked the other."""
    found = await conn.scalar(
        text(
            "SELECT 1 FROM blocks WHERE (blocker_id = :a AND blocked_id = :b)"
            " OR (blocker_id = :b AND blocked_id = :a)"
        ),
        {"a": a, "b": b},
    )
    return found is not None


async def _one(conn: AsyncConnection, conversation_id: uuid.UUID, me: uuid.UUID) -> ConversationOut:
    """Load one chat as seen by me."""
    row = (
        await conn.execute(text(_LIST + " AND c.id = :c"), {"me": me, "c": conversation_id})
    ).one_or_none()
    if row is None:
        raise _not_found()
    return ConversationOut(**row._mapping)


async def _my_membership(
    conn: AsyncConnection, conversation_id: uuid.UUID, me: uuid.UUID
) -> tuple[str, str, str]:
    """(kind, state, role) of an invited or active membership; 404 otherwise."""
    row = (
        await conn.execute(
            text(
                "SELECT c.kind, m.state, m.role FROM conversations c"
                " JOIN conversation_members m ON m.conversation_id = c.id AND m.user_id = :me"
                " WHERE c.id = :c AND m.state IN ('invited', 'active')"
            ),
            {"me": me, "c": conversation_id},
        )
    ).one_or_none()
    if row is None:
        raise _not_found()
    return row.kind, row.state, row.role


async def active_member(conn: AsyncConnection, conversation_id: uuid.UUID, me: uuid.UUID) -> str:
    """The chat's kind if I am an active member; 404 otherwise (invited people see no content)."""
    kind, state, _ = await _my_membership(conn, conversation_id, me)
    if state != "active":
        raise _not_found()
    return kind


async def _notify_members(
    request: Request, conversation_id: uuid.UUID, extra: list[uuid.UUID]
) -> None:
    """Tell everyone in the chat that its members changed."""
    async with request.app.state.db.connect() as conn:
        ids = await chat_events.member_ids(conn, conversation_id)
    await chat_events.publish(request.app.state.redis, ids + extra, conversation_id, "members")


async def _require_admin(conn: AsyncConnection, conversation_id: uuid.UUID, me: uuid.UUID) -> None:
    """Refuse unless I am an admin of this cluster."""
    kind, state, role = await _my_membership(conn, conversation_id, me)
    if kind != "cluster" or state != "active" or role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a cluster admin can do that")


async def _invite(
    conn: AsyncConnection, conversation_id: uuid.UUID, me: uuid.UUID, handles: list[str]
) -> list[str]:
    """Invite people; returns the handles that could not be invited (never says why)."""
    skipped: list[str] = []
    for handle in dict.fromkeys(handles):
        people = await conn.scalar(
            text(
                "SELECT count(*) FROM conversation_members"
                " WHERE conversation_id = :c AND state IN ('invited', 'active')"
            ),
            {"c": conversation_id},
        )
        uid = await _user_id(conn, handle)
        full = people >= MAX_PEOPLE
        if uid is None or uid == me or full or await _blocked_between(conn, me, uid):
            skipped.append(handle)
            continue
        await conn.execute(
            text(
                "INSERT INTO conversation_members (conversation_id, user_id, state, invited_by)"
                " VALUES (:c, :u, 'invited', :me)"
                " ON CONFLICT (conversation_id, user_id) DO UPDATE"
                " SET state = 'invited', invited_by = :me, invited_at = now(), role = 'member'"
                " WHERE conversation_members.state = 'left'"
            ),
            {"c": conversation_id, "u": uid, "me": me},
        )
    return skipped


@router.get("/conversations")
async def my_conversations(request: Request, user: Me) -> list[ConversationOut]:
    """Your private clusters, direct chats, pending invitations and message requests."""
    human(user)
    async with request.app.state.db.connect() as conn:
        rows = await conn.execute(
            text(_LIST + " ORDER BY me.state DESC, c.created_at DESC LIMIT 200"), {"me": user.id}
        )
    return [ConversationOut(**r._mapping) for r in rows]


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def create_cluster(body: ClusterIn, request: Request, user: Me) -> Created:
    """A private cluster: you are its admin; everyone you add gets an invitation to accept."""
    human(user)
    await ratelimit.enforce(request, f"ratelimit:conv:new:{user.id}", CREATE_LIMIT, CREATE_WINDOW)
    await ratelimit.enforce(request, f"ratelimit:conv:inv:{user.id}", INVITE_LIMIT, INVITE_WINDOW)
    async with request.app.state.db.begin() as conn:
        cid = await conn.scalar(
            text(
                "INSERT INTO conversations (kind, name, created_by)"
                " VALUES ('cluster', :n, :me) RETURNING id"
            ),
            {"n": body.name, "me": user.id},
        )
        await conn.execute(
            text(
                "INSERT INTO conversation_members"
                " (conversation_id, user_id, role, state, joined_at)"
                " VALUES (:c, :me, 'admin', 'active', now())"
            ),
            {"c": cid, "me": user.id},
        )
        skipped = await _invite(conn, cid, user.id, body.members)
        out = await _one(conn, cid, user.id)
    await _notify_members(request, cid, [])
    metrics.chat_event("conversation")
    return Created(conversation=out, not_invited=skipped)


@router.post("/conversations/direct", status_code=status.HTTP_201_CREATED)
async def start_direct(body: DirectIn, request: Request, user: Me) -> ConversationOut:
    """Start (or reopen) a one-to-one chat."""
    human(user)
    await ratelimit.enforce(request, f"ratelimit:conv:new:{user.id}", CREATE_LIMIT, CREATE_WINDOW)
    async with request.app.state.db.begin() as conn:
        other = await _user_id(conn, body.handle)
        if other is None or other == user.id or await _blocked_between(conn, user.id, other):
            raise _not_found()
        low, high = sorted((user.id, other), key=str)
        cid = await conn.scalar(
            text(
                "INSERT INTO conversations (kind, created_by, direct_low, direct_high)"
                " VALUES ('direct', :me, :lo, :hi)"
                " ON CONFLICT (direct_low, direct_high)"
                " DO UPDATE SET ai_enabled = conversations.ai_enabled"
                " RETURNING id"
            ),
            {"me": user.id, "lo": low, "hi": high},
        )
        await conn.execute(
            text(
                "INSERT INTO conversation_members (conversation_id, user_id, state, joined_at)"
                " VALUES (:c, :me, 'active', now())"
                " ON CONFLICT (conversation_id, user_id) DO UPDATE"
                " SET state = 'active', joined_at = coalesce(conversation_members.joined_at, now())"
            ),
            {"c": cid, "me": user.id},
        )
        await conn.execute(
            text(
                "INSERT INTO conversation_members (conversation_id, user_id, state, invited_by)"
                " VALUES (:c, :u, 'invited', :me) ON CONFLICT (conversation_id, user_id) DO UPDATE"
                " SET state = 'invited', invited_by = :me, invited_at = now()"
                " WHERE conversation_members.state = 'left'"
            ),
            {"c": cid, "u": other, "me": user.id},
        )
        out = await _one(conn, cid, user.id)
    await _notify_members(request, cid, [])
    metrics.chat_event("conversation")
    return out


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID, request: Request, user: Me
) -> ConversationDetail:
    """Show one chat with its members."""
    human(user)
    async with request.app.state.db.connect() as conn:
        out = await _one(conn, conversation_id, user.id)
        members: list[Member] = []
        if out.my_state == "active":
            rows = await conn.execute(
                text(
                    "SELECT u.handle, m.role, m.state FROM conversation_members m"
                    " JOIN users u ON u.id = m.user_id"
                    " WHERE m.conversation_id = :c AND m.state IN ('invited', 'active')"
                    " ORDER BY m.state, m.role, u.handle"
                ),
                {"c": conversation_id},
            )
            members = [Member(**r._mapping) for r in rows]
    return ConversationDetail(**out.model_dump(), members=members)


@router.post("/conversations/{conversation_id}/accept")
async def accept(conversation_id: uuid.UUID, request: Request, user: Me) -> ConversationOut:
    """Accept an invitation or message request."""
    human(user)
    async with request.app.state.db.begin() as conn:
        _, state, _ = await _my_membership(conn, conversation_id, user.id)
        if state == "invited":
            await conn.execute(
                text(
                    "UPDATE conversation_members SET state = 'active', joined_at = now()"
                    " WHERE conversation_id = :c AND user_id = :me"
                ),
                {"c": conversation_id, "me": user.id},
            )
        out = await _one(conn, conversation_id, user.id)
    await _notify_members(request, conversation_id, [])
    return out


@router.post("/conversations/{conversation_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
async def decline(conversation_id: uuid.UUID, request: Request, user: Me) -> None:
    """Decline an invitation or message request."""
    human(user)
    async with request.app.state.db.begin() as conn:
        _, state, _ = await _my_membership(conn, conversation_id, user.id)
        if state != "invited":
            raise HTTPException(status.HTTP_409_CONFLICT, "Not an invitation; leave instead")
        await conn.execute(
            text("DELETE FROM conversation_members WHERE conversation_id = :c AND user_id = :me"),
            {"c": conversation_id, "me": user.id},
        )
    await _notify_members(request, conversation_id, [])


@router.post("/conversations/{conversation_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave(conversation_id: uuid.UUID, request: Request, user: Me) -> None:
    """Leave a chat."""
    human(user)
    async with request.app.state.db.begin() as conn:
        await _my_membership(conn, conversation_id, user.id)
        await conn.execute(
            text(
                "UPDATE conversation_members SET state = 'left', role = 'member'"
                " WHERE conversation_id = :c AND user_id = :me"
            ),
            {"c": conversation_id, "me": user.id},
        )
        await _keep_an_admin(conn, conversation_id)
    await _notify_members(request, conversation_id, [])


async def _keep_an_admin(conn: AsyncConnection, conversation_id: uuid.UUID) -> None:
    """Make sure a cluster always has an admin."""
    await conn.execute(
        text(
            "UPDATE conversation_members SET role = 'admin'"
            " WHERE conversation_id = :c AND user_id = ("
            "   SELECT m.user_id FROM conversation_members m"
            "   JOIN conversations c ON c.id = m.conversation_id"
            "   WHERE m.conversation_id = :c AND c.kind = 'cluster' AND m.state = 'active'"
            "   AND NOT EXISTS (SELECT 1 FROM conversation_members a WHERE a.conversation_id = :c"
            "                   AND a.state = 'active' AND a.role = 'admin')"
            "   ORDER BY m.joined_at LIMIT 1)"
        ),
        {"c": conversation_id},
    )


@router.patch("/conversations/{conversation_id}")
async def update_cluster(
    conversation_id: uuid.UUID,
    body: ClusterPatch,
    request: Request,
    user: Me,
) -> ConversationOut:
    """Admins rename a cluster or switch its AI on/off."""
    human(user)
    async with request.app.state.db.begin() as conn:
        await _require_admin(conn, conversation_id, user.id)
        if body.name is not None:
            await conn.execute(
                text("UPDATE conversations SET name = :n WHERE id = :c"),
                {"n": body.name, "c": conversation_id},
            )
        if body.ai_enabled is not None:
            await conn.execute(
                text("UPDATE conversations SET ai_enabled = :a WHERE id = :c"),
                {"a": body.ai_enabled, "c": conversation_id},
            )
        if body.ai_sharing is not None:
            await conn.execute(
                text("UPDATE conversations SET ai_sharing = :s WHERE id = :c"),
                {"s": body.ai_sharing, "c": conversation_id},
            )
        return await _one(conn, conversation_id, user.id)


@router.post("/conversations/{conversation_id}/members")
async def invite_members(
    conversation_id: uuid.UUID,
    body: InviteIn,
    request: Request,
    user: Me,
) -> dict[str, list[str]]:
    """Invite people to a cluster."""
    human(user)
    await ratelimit.enforce(request, f"ratelimit:conv:inv:{user.id}", INVITE_LIMIT, INVITE_WINDOW)
    async with request.app.state.db.begin() as conn:
        await _require_admin(conn, conversation_id, user.id)
        skipped = await _invite(conn, conversation_id, user.id, body.handles)
    await _notify_members(request, conversation_id, [])
    return {"not_invited": skipped}


@router.delete(
    "/conversations/{conversation_id}/members/{handle}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_member(
    conversation_id: uuid.UUID,
    handle: Handle,
    request: Request,
    user: Me,
) -> None:
    """Admins remove a member or cancel an invitation (leaving yourself: POST .../leave)."""
    human(user)
    async with request.app.state.db.begin() as conn:
        await _require_admin(conn, conversation_id, user.id)
        uid = await _user_id(conn, handle)
        if uid is None or uid == user.id:
            raise _not_found()
        done = await conn.execute(
            text(
                "UPDATE conversation_members SET state = 'left', role = 'member'"
                " WHERE conversation_id = :c AND user_id = :u AND state IN ('invited', 'active')"
            ),
            {"c": conversation_id, "u": uid},
        )
        if done.rowcount == 0:
            raise _not_found()
    await _notify_members(request, conversation_id, [uid])


@router.put("/conversations/{conversation_id}/members/{handle}/role")
async def set_role(
    conversation_id: uuid.UUID,
    handle: Handle,
    body: RoleIn,
    request: Request,
    user: Me,
) -> dict[str, str]:
    """Make a member an admin or a regular member."""
    human(user)
    async with request.app.state.db.begin() as conn:
        await _require_admin(conn, conversation_id, user.id)
        uid = await _user_id(conn, handle)
        done = await conn.execute(
            text(
                "UPDATE conversation_members SET role = :r"
                " WHERE conversation_id = :c AND user_id = :u AND state = 'active'"
            ),
            {"r": body.role, "c": conversation_id, "u": uid},
        )
        if uid is None or done.rowcount == 0:
            raise _not_found()
        await _keep_an_admin(conn, conversation_id)
    return {"handle": handle, "role": body.role}


@router.get("/me/blocks")
async def my_blocks(request: Request, user: Me) -> list[str]:
    """List the people I blocked."""
    human(user)
    async with request.app.state.db.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT u.handle FROM blocks b JOIN users u ON u.id = b.blocked_id"
                " WHERE b.blocker_id = :me ORDER BY b.created_at DESC"
            ),
            {"me": user.id},
        )
    return [r.handle for r in rows]


@router.put("/me/blocks/{handle}", status_code=status.HTTP_204_NO_CONTENT)
async def block(handle: Handle, request: Request, user: Me) -> None:
    """Block someone from inviting or messaging me."""
    human(user)
    async with request.app.state.db.begin() as conn:
        uid = await _user_id(conn, handle)
        if uid is None or uid == user.id:
            raise _not_found()
        await conn.execute(
            text(
                "INSERT INTO blocks (blocker_id, blocked_id) VALUES (:me, :u)"
                " ON CONFLICT DO NOTHING"
            ),
            {"me": user.id, "u": uid},
        )
        removed = await conn.execute(
            text(
                "DELETE FROM conversation_members WHERE state = 'invited' AND ("
                " (user_id = :me AND invited_by = :u) OR (user_id = :u AND invited_by = :me))"
                " RETURNING conversation_id"
            ),
            {"me": user.id, "u": uid},
        )
        chats = {r.conversation_id for r in removed}
    for c in chats:
        await _notify_members(request, c, [uid, user.id])


@router.delete("/me/blocks/{handle}", status_code=status.HTTP_204_NO_CONTENT)
async def unblock(handle: Handle, request: Request, user: Me) -> None:
    """Unblock a person."""
    human(user)
    async with request.app.state.db.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM blocks WHERE blocker_id = :me"
                " AND blocked_id = (SELECT id FROM users WHERE handle = :h)"
            ),
            {"me": user.id, "h": handle},
        )


@router.get("/people")
async def find_people(
    q: Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{2,30}$")],
    request: Request,
    user: Me,
) -> list[str]:
    """Handles starting with `q`, for picking people (handles are public already)."""
    human(user)
    await ratelimit.enforce(request, f"ratelimit:people:{user.id}", 60, 60)
    async with request.app.state.db.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT u.handle FROM users u WHERE u.handle LIKE :p AND u.id <> :me"
                " AND NOT EXISTS (SELECT 1 FROM blocks b"
                "   WHERE (b.blocker_id = :me AND b.blocked_id = u.id)"
                "   OR (b.blocker_id = u.id AND b.blocked_id = :me))"
                " ORDER BY u.handle LIMIT 8"
            ),
            {"p": q + "%", "me": user.id},
        )
    return [r.handle for r in rows]
