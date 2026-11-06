"""Shared test helpers: a test signing key, and throwaway data on beta (when tunnels are open)."""

import asyncio
import hashlib
import os
import socket
import uuid
from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from api.auth import issue_token
from api.config import get_settings

TEST_KEY = "test-key-" + "x" * 55  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def signing_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Use a test key for sign-in tokens."""
    monkeypatch.setenv("JWT_SIGNING_KEY", TEST_KEY)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def auth_header(user_id: uuid.UUID, handle: str = "tester") -> dict[str, str]:
    """A sign-in header for a test person."""
    return {"Authorization": f"Bearer {issue_token(user_id, handle)}"}


def _port_open(port: int) -> bool:
    """Whether a local port is open."""
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


beta = pytest.mark.skipif(
    not (_port_open(15432) and _port_open(16379) and os.environ.get("TEST_OWNER_PASSWORD")),
    reason="needs make db-tunnel + make redis-tunnel, run via make test",
)


def run_sql(statement: str, params: dict[str, object], *, as_owner: bool = False) -> None:
    """Test setup/cleanup."""
    url = get_settings().database_url
    connect_args: dict[str, object] = {}
    if as_owner:
        url = url.replace("platform_v2_app@", "platform_v2_owner@")
        connect_args["password"] = os.environ["TEST_OWNER_PASSWORD"]

    async def run() -> None:
        """Run the statement."""
        engine = create_async_engine(url, connect_args=connect_args)
        try:
            async with engine.begin() as conn:
                await conn.execute(text(statement), params)
        finally:
            await engine.dispose()

    asyncio.run(run())


@pytest.fixture
def beta_user() -> Iterator[tuple[uuid.UUID, str]]:
    """A throwaway dev user; it and everything it created are removed afterwards."""
    user_id, handle = uuid.uuid4(), f"zz-test-{uuid.uuid4().hex[:8]}"
    run_sql(
        "INSERT INTO users (id, handle, auth_provider, provider_user_id_hash)"
        " VALUES (:id, :handle, 'dev', :h)",
        {"id": user_id, "handle": handle, "h": hashlib.sha256(handle.encode()).hexdigest()},
    )
    yield user_id, handle
    run_sql("DELETE FROM drafts WHERE user_id = :id", {"id": user_id}, as_owner=True)
    run_sql("DELETE FROM access_tokens WHERE user_id = :id", {"id": user_id}, as_owner=True)
    run_sql("DELETE FROM replies WHERE author_id = :id", {"id": user_id}, as_owner=True)
    run_sql("DELETE FROM threads WHERE author_id = :id", {"id": user_id}, as_owner=True)
    run_sql("DELETE FROM topic_groups WHERE created_by = :id", {"id": user_id}, as_owner=True)
    run_sql("DELETE FROM users WHERE id = :id", {"id": user_id}, as_owner=True)


def use_real_safety(app: FastAPI) -> None:
    """Point the api at the real safety service, running in-process (no network, no fakes)."""
    from safety.main import create_app as create_safety_app

    app.state.safety = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_safety_app()), base_url="http://safety"
    )
