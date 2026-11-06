"""GET /me: who the token belongs to, and whether they accepted the current Terms."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from api.auth import CurrentUser, current_user, unauthorized
from api.routes.signin import TERMS_VERSION

router = APIRouter()


class TermsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str


@router.get("/me")
async def me(
    request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> dict[str, str | bool | None]:
    """Also checks the user still exists: a valid token can outlive a deleted user."""
    async with request.app.state.db.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT terms_version FROM users WHERE id = :id"), {"id": user.id}
            )
        ).one_or_none()
    if row is None:
        raise unauthorized()
    return {
        "id": str(user.id),
        "handle": user.handle,
        "terms_version": row.terms_version,
        "terms_current": row.terms_version == TERMS_VERSION,
    }


@router.post("/me/terms", status_code=status.HTTP_204_NO_CONTENT)
async def accept_terms(
    body: TermsIn, request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> None:
    """Records consent to the version the person was shown; only a person can give it."""
    if user.actor != "human":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only you can accept the Terms")
    if body.version != TERMS_VERSION:
        raise HTTPException(status.HTTP_409_CONFLICT, "The terms changed, please reload the page")
    async with request.app.state.db.begin() as conn:
        await conn.execute(
            text("UPDATE users SET terms_version = :v, terms_accepted_at = now() WHERE id = :id"),
            {"v": TERMS_VERSION, "id": user.id},
        )
