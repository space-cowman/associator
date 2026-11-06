import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.auth import (
    ALGORITHM,
    AUDIENCE,
    ISSUER,
    CurrentUser,
    current_user,
    issue_token,
    verify_token,
)
from api.config import get_settings

KEY = "test-key-" + "x" * 55  # pragma: allowlist secret
USER_ID = uuid.uuid4()


@pytest.fixture(autouse=True)
def signing_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Use a test key for sign-in tokens."""
    monkeypatch.setenv("JWT_SIGNING_KEY", KEY)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    """A test app with one private route."""
    app = FastAPI()

    @app.get("/private")
    async def private(user: Annotated[CurrentUser, Depends(current_user)]) -> dict[str, str]:
        """A route that needs sign-in."""
        return {"id": str(user.id), "handle": user.handle}

    return TestClient(app)


def _claims(**override: Any) -> dict[str, Any]:
    """Valid token claims for tests."""
    now = datetime.now(UTC)
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(USER_ID),
        "handle": "alice",
        "act": "human",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    claims.update(override)
    return {k: v for k, v in claims.items() if v is not None}


def test_valid_token(client: TestClient) -> None:
    """Valid token."""
    token = issue_token(USER_ID, "alice")
    response = client.get("/private", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"id": str(USER_ID), "handle": "alice"}


BAD_TOKENS = {
    "expired": jwt.encode(
        _claims(exp=datetime.now(UTC) - timedelta(minutes=5)), KEY, algorithm=ALGORITHM
    ),
    "other key": jwt.encode(_claims(), "another-key-" + "y" * 52, algorithm=ALGORITHM),
    "unsigned alg=none": jwt.encode(_claims(), None, algorithm="none"),
    "wrong audience": jwt.encode(_claims(aud="other-service"), KEY, algorithm=ALGORITHM),
    "missing handle": jwt.encode(_claims(handle=None), KEY, algorithm=ALGORITHM),
    "sub not a uuid": jwt.encode(_claims(sub="admin"), KEY, algorithm=ALGORITHM),
    "missing actor": jwt.encode(_claims(act=None), KEY, algorithm=ALGORITHM),
    "unknown actor": jwt.encode(_claims(act="admin"), KEY, algorithm=ALGORITHM),
}


@pytest.mark.parametrize("header", [None, *BAD_TOKENS.values()], ids=["no token", *BAD_TOKENS])
def test_rejected_with_same_401(client: TestClient, header: str | None) -> None:
    """Rejected with same 401."""
    headers = {"Authorization": f"Bearer {header}"} if header else {}
    response = client.get("/private", headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_agent_token_carries_actor() -> None:
    """Agent token carries actor."""
    assert verify_token(issue_token(USER_ID, "alice", "agent")).actor == "agent"
    assert verify_token(issue_token(USER_ID, "alice")).actor == "human"
    with pytest.raises(ValueError):
        issue_token(USER_ID, "alice", "admin")
