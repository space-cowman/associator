"""Topic groups: anyone can list; any signed-in user can create (rate-limited)."""

import re
import unicodedata
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api import ratelimit
from api.auth import CurrentUser, current_user, optional_user
from api.validation import visible_text_only
from api.visibility import VISIBLE_TO_VIEWER, ensure_visible

router = APIRouter(prefix="/groups")

CREATE_LIMIT = 5
CREATE_WINDOW_SECONDS = 24 * 3600
LIST_LIMIT = 200

RESERVED_SLUGS = frozenset(
    {
        "admin",
        "administrator",
        "api",
        "auth",
        "groups",
        "me",
        "mod",
        "moderator",
        "official",
        "platform",
        "platform-v2",
        "root",
        "security",
        "settings",
        "staff",
        "support",
        "system",
    }
)


def slug_from(name: str) -> str:
    """The link part of a group, made from its name: "DevOps Tips" -> "devops-tips"."""
    ascii_only = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")[:36].strip("-")


Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=60),
    AfterValidator(visible_text_only),
]
Description = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    AfterValidator(visible_text_only),
]


class GroupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    description: Description | None = None


class GroupOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    member_count: int = 0
    thread_count: int = 0
    joined: bool = False


_LIST = """
    SELECT g.id, g.slug, g.name, g.description,
           (SELECT count(*) FROM group_members m WHERE m.group_id = g.id) AS member_count,
           (SELECT count(*) FROM threads t WHERE t.group_id = g.id AND t.deleted_at IS NULL)
             AS thread_count,
           EXISTS (SELECT 1 FROM group_members m WHERE m.group_id = g.id AND m.user_id = :me)
             AS joined
    FROM topic_groups g
"""


@router.get("")
async def list_groups(
    request: Request, user: Annotated[CurrentUser | None, Depends(optional_user)]
) -> list[GroupOut]:
    """List the clusters."""
    async with request.app.state.db.connect() as conn:
        rows = await conn.execute(
            text(_LIST + f" WHERE {VISIBLE_TO_VIEWER} ORDER BY g.slug LIMIT :limit"),
            {
                "limit": LIST_LIMIT,
                "me": user.id if user else None,
                "viewer": user.id if user else None,
            },
        )
    return [GroupOut(**r._mapping) for r in rows]


@router.get("/{slug}")
async def get_group(
    slug: str, request: Request, user: Annotated[CurrentUser | None, Depends(optional_user)]
) -> GroupOut:
    """Show one cluster."""
    async with request.app.state.db.connect() as conn:
        await ensure_visible(conn, user.id if user else None, slug=slug)
    async with request.app.state.db.connect() as conn:
        row = (
            await conn.execute(
                text(_LIST + " WHERE g.slug = :slug"),  # noqa: S608
                {"slug": slug, "me": user.id if user else None},
            )
        ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")
    return GroupOut(**row._mapping)


@router.put("/{slug}/membership", status_code=status.HTTP_204_NO_CONTENT)
async def join_group(
    slug: str, request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> None:
    """Join a cluster."""
    async with request.app.state.db.connect() as conn:
        await ensure_visible(conn, user.id, slug=slug)
    async with request.app.state.db.begin() as conn:
        group_id = await conn.scalar(
            text("SELECT id FROM topic_groups WHERE slug = :s"), {"s": slug}
        )
        if group_id is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")
        await conn.execute(
            text(
                "INSERT INTO group_members (group_id, user_id) VALUES (:g, :u)"
                " ON CONFLICT DO NOTHING"
            ),
            {"g": group_id, "u": user.id},
        )


@router.delete("/{slug}/membership", status_code=status.HTTP_204_NO_CONTENT)
async def leave_group(
    slug: str, request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> None:
    """Leave a cluster."""
    async with request.app.state.db.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM group_members WHERE user_id = :u"
                " AND group_id = (SELECT id FROM topic_groups WHERE slug = :slug)"
            ),
            {"u": user.id, "slug": slug},
        )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_group(
    body: GroupIn, request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> GroupOut:
    """Create a cluster."""
    await ratelimit.enforce(
        request, f"ratelimit:groups:create:{user.id}", CREATE_LIMIT, CREATE_WINDOW_SECONDS
    )
    base = slug_from(body.name)
    if len(base) < 2:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Use at least 2 letters or digits in the name"
        )
    if base in RESERVED_SLUGS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That name is reserved")
    for attempt in range(1, 10):
        slug = base if attempt == 1 else f"{base}-{attempt}"
        try:
            async with request.app.state.db.begin() as conn:
                row = (
                    await conn.execute(
                        text(
                            "INSERT INTO topic_groups (slug, name, description, created_by)"
                            " VALUES (:slug, :name, :description, :uid)"
                            " RETURNING id, slug, name, description"
                        ),
                        {
                            "slug": slug,
                            "name": body.name,
                            "description": body.description,
                            "uid": user.id,
                        },
                    )
                ).one()
                await conn.execute(
                    text("INSERT INTO group_members (group_id, user_id) VALUES (:g, :u)"),
                    {"g": row.id, "u": user.id},
                )
            break
        except IntegrityError:
            continue
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, "Too many groups with this name")
    return GroupOut(**row._mapping, member_count=1, joined=True)
