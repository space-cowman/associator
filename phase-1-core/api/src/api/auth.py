"""Access tokens: HS256 JWT, 15 minutes."""

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from api.config import get_settings

ISSUER = "platform-v2"
AUDIENCE = "platform-v2-api"
ALGORITHM = "HS256"
TTL = timedelta(minutes=15)
REQUIRED_CLAIMS = ["iss", "aud", "sub", "handle", "act", "iat", "exp"]
ACTORS = ("human", "agent")
ACCESS_TOKEN = re.compile(r"^sop_[A-Za-z0-9_-]{43}$")

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    handle: str
    actor: str


def unauthorized() -> HTTPException:
    """Same answer for every failure: the caller never learns which check failed."""
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"}
    )


def _key() -> str:
    """The key that signs sign-in tokens."""
    key = get_settings().jwt_signing_key
    if key is None:
        raise RuntimeError("JWT_SIGNING_KEY is not set")
    return key.get_secret_value()


def issue_token(user_id: uuid.UUID, handle: str, actor: str = "human", ttl: timedelta = TTL) -> str:
    """Make a signed sign-in token for a person."""
    if actor not in ACTORS:
        raise ValueError("unknown actor")
    now = datetime.now(UTC)
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(user_id),
        "handle": handle,
        "act": actor,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(claims, _key(), algorithm=ALGORITHM)


def verify_token(token: str) -> CurrentUser:
    """Check a token; return its user."""
    claims = jwt.decode(
        token,
        _key(),
        algorithms=[ALGORITHM],
        audience=AUDIENCE,
        issuer=ISSUER,
        leeway=30,
        options={"require": REQUIRED_CLAIMS},
    )
    if claims["act"] not in ACTORS:
        raise jwt.InvalidTokenError("unknown actor")
    return CurrentUser(
        id=uuid.UUID(claims["sub"]), handle=str(claims["handle"]), actor=claims["act"]
    )


def hash_access_token(token: str) -> str:
    """Tokens are 256 random bits, so a fast hash is safe; only the hash is stored."""
    return hashlib.sha256(token.encode()).hexdigest()


async def _verify_access_token(request: Request, token: str) -> CurrentUser | None:
    """A valid, unrevoked, unexpired token -> its owner, acting as "agent"."""
    if not ACCESS_TOKEN.fullmatch(token):
        return None
    async with request.app.state.db.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "UPDATE access_tokens a SET last_used_at = now() FROM users u"
                    " WHERE a.token_hash = :h AND u.id = a.user_id"
                    " AND a.revoked_at IS NULL AND a.expires_at > now()"
                    " RETURNING u.id, u.handle"
                ),
                {"h": hash_access_token(token)},
            )
        ).one_or_none()
    return CurrentUser(id=row.id, handle=row.handle, actor="agent") if row else None


async def current_user(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    """Dependency: add `user: Annotated[CurrentUser, Depends(current_user)]` to protect a route."""
    if creds is None:
        raise unauthorized()
    if creds.credentials.startswith("sop_"):
        user = await _verify_access_token(request, creds.credentials)
        if user is None:
            raise unauthorized()
        return user
    try:
        return verify_token(creds.credentials)
    except (jwt.InvalidTokenError, ValueError):
        raise unauthorized() from None


async def optional_user(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser | None:
    """The signed-in person, or None for visitors."""
    if creds is None:
        return None
    try:
        return await current_user(request, creds)
    except HTTPException:
        return None
