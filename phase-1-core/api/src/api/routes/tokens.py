"""Personal access tokens for a user's own AI app (MCP)."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from api import ratelimit
from api.auth import CurrentUser, current_user, hash_access_token

router = APIRouter(prefix="/me/tokens")

TOKEN_DAYS = 90
MAX_ACTIVE = 5
CREATE_LIMIT = 10


class TokenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z0-9 ._-]{1,40}$")


class TokenOut(BaseModel):
    id: uuid.UUID
    name: str
    token_last4: str
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class TokenCreated(TokenOut):
    token: str


_COLUMNS = "id, name, token_last4, created_at, expires_at, last_used_at, revoked_at"


def _human(user: CurrentUser) -> None:
    """Only the person, not an AI app, may do this."""
    if user.actor != "human":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only you can manage access tokens")


@router.get("")
async def list_tokens(
    request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> list[TokenOut]:
    """List my access tokens."""
    _human(user)
    async with request.app.state.db.connect() as conn:
        rows = await conn.execute(
            text(f"SELECT {_COLUMNS} FROM access_tokens WHERE user_id = :u ORDER BY created_at"),  # noqa: S608
            {"u": user.id},
        )
    return [TokenOut(**r._mapping) for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_token(
    body: TokenIn, request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> TokenCreated:
    """Create an access token for an AI app."""
    _human(user)
    await ratelimit.enforce(request, f"ratelimit:tokens:{user.id}", CREATE_LIMIT, 3600)
    token = "sop_" + secrets.token_urlsafe(32)
    async with request.app.state.db.begin() as conn:
        active = await conn.scalar(
            text(
                "SELECT count(*) FROM access_tokens"
                " WHERE user_id = :u AND revoked_at IS NULL AND expires_at > now()"
            ),
            {"u": user.id},
        )
        if active >= MAX_ACTIVE:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"At most {MAX_ACTIVE} active tokens; revoke one first"
            )
        row = (
            await conn.execute(
                text(
                    "INSERT INTO access_tokens (user_id, name, token_hash, token_last4, expires_at)"
                    " VALUES (:u, :name, :hash, :last4, :expires)"
                    " RETURNING id, name, token_last4, created_at, expires_at, last_used_at,"
                    " revoked_at"
                ),
                {
                    "u": user.id,
                    "name": body.name,
                    "hash": hash_access_token(token),
                    "last4": token[-4:],
                    "expires": datetime.now(UTC) + timedelta(days=TOKEN_DAYS),
                },
            )
        ).one()
    return TokenCreated(**row._mapping, token=token)


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(
    token_id: uuid.UUID, request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> None:
    """Revoke an access token."""
    _human(user)
    async with request.app.state.db.begin() as conn:
        revoked = await conn.execute(
            text(
                "UPDATE access_tokens SET revoked_at = now()"
                " WHERE id = :id AND user_id = :u AND revoked_at IS NULL"
            ),
            {"id": token_id, "u": user.id},
        )
    if revoked.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
