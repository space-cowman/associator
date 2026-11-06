"""Live end-to-end tests against the deployed site (Phase 1 `TESTS.md`)."""

import asyncio
import hashlib
import json
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

BASE = os.environ.get("E2E_BASE_URL", "")
live = pytest.mark.skipif(not BASE, reason="live tests: run via make e2e")

DB = "postgresql+psycopg://{user}@127.0.0.1:15432/platform_v2"


def sql(statement: str, params: dict[str, object], *, owner: bool = False) -> list[tuple]:
    """Setup as the app role; cleanup as the owner (the app role cannot delete posts)."""
    role = "platform_v2_owner" if owner else "platform_v2_app"
    password = os.environ["TEST_OWNER_PASSWORD" if owner else "PGPASSWORD"]

    async def run() -> list[tuple]:
        """Run the statement."""
        engine = create_async_engine(DB.format(user=role), connect_args={"password": password})
        try:
            async with engine.begin() as conn:
                result = await conn.execute(text(statement), params)
                return list(result.fetchall()) if result.returns_rows else []
        finally:
            await engine.dispose()

    return asyncio.run(run())


@dataclass
class User:
    id: uuid.UUID
    handle: str
    token: str
    agent_token: str

    @property
    def h(self) -> dict[str, str]:
        """Sign-in header as a person."""
        return {"Authorization": f"Bearer {self.token}"}

    @property
    def agent(self) -> dict[str, str]:
        """Sign-in header as the person's AI app."""
        return {"Authorization": f"Bearer {self.agent_token}"}


def make_user(handle: str) -> User:
    """Create a throwaway person."""
    from api.auth import issue_token

    pid = hashlib.sha256(f"dev:{handle}".encode()).hexdigest()
    (row,) = sql(
        "INSERT INTO users (handle, auth_provider, provider_user_id_hash) VALUES (:h, 'dev', :p)"
        " RETURNING id",
        {"h": handle, "p": pid},
    )
    user_id = row[0]
    hour = timedelta(hours=1)
    return User(
        user_id,
        handle,
        issue_token(user_id, handle, "human", hour),
        issue_token(user_id, handle, "agent", hour),
    )


def cleanup(handles: list[str], cluster_slugs: list[str]) -> None:
    """Remove the test people and what they made."""
    ids = {"h": handles}
    for statement in (
        "DELETE FROM notifications WHERE user_id IN (SELECT id FROM users WHERE handle = ANY(:h))"
        " OR actor_id IN (SELECT id FROM users WHERE handle = ANY(:h))",
        "DELETE FROM conversations"
        " WHERE created_by IN (SELECT id FROM users WHERE handle = ANY(:h))",
        "DELETE FROM drafts WHERE user_id IN (SELECT id FROM users WHERE handle = ANY(:h))",
        "DELETE FROM access_tokens WHERE user_id IN (SELECT id FROM users WHERE handle = ANY(:h))",
        "DELETE FROM model_registry WHERE user_id IN (SELECT id FROM users WHERE handle = ANY(:h))",
        "DELETE FROM attachments WHERE owner_id IN (SELECT id FROM users WHERE handle = ANY(:h))",
        "DELETE FROM replies WHERE author_id IN (SELECT id FROM users WHERE handle = ANY(:h))",
        "DELETE FROM threads WHERE author_id IN (SELECT id FROM users WHERE handle = ANY(:h))",
    ):
        sql(statement, ids, owner=True)
    sql("DELETE FROM topic_groups WHERE slug = ANY(:s)", {"s": cluster_slugs}, owner=True)
    sql("DELETE FROM users WHERE handle = ANY(:h)", ids, owner=True)


@pytest.fixture(scope="session")
def site() -> Iterator[dict[str, object]]:
    """Three people (asker, answerer, voter) and a throwaway cluster, removed afterwards."""
    if not BASE:
        pytest.skip("live tests: run via make e2e")
    tag = uuid.uuid4().hex[:6]
    handles = [f"zz-e2e-{tag}-a", f"zz-e2e-{tag}-b", f"zz-e2e-{tag}-c"]
    users = [make_user(h) for h in handles]
    client = httpx.Client(base_url=f"{BASE}/api", timeout=120, follow_redirects=False)
    slugs: list[str] = []
    try:
        created = client.post("/groups", json={"name": f"zz e2e {tag}"}, headers=users[0].h)
        assert created.status_code == 201, created.text
        slugs.append(created.json()["slug"])
        sql("UPDATE topic_groups SET hidden = true WHERE slug = :s", {"s": slugs[0]}, owner=True)
        for member in users[1:]:
            sql(
                "INSERT INTO group_members (group_id, user_id)"
                " SELECT id, :u FROM topic_groups WHERE slug = :s",
                {"u": member.id, "s": slugs[0]},
                owner=True,
            )
        yield {"client": client, "a": users[0], "b": users[1], "c": users[2], "cluster": slugs[0]}
    finally:
        client.close()
        cleanup(handles, slugs)


@pytest.fixture(scope="session")
def owner_sql():  # type: ignore[no-untyped-def]
    """Read the database as the owner role (what moderation sees)."""
    return lambda statement, params: sql(statement, params, owner=True)


def _parse(response: httpx.Response) -> dict[str, Any]:
    """The server answers with JSON or with one Server-Sent Event carrying the JSON."""
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        for line in response.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:])
        raise AssertionError("no data in event stream")
    return response.json()


def _mcp_call(base: str, token: str | None, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Call one MCP tool on the live site."""
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": "2025-06-18",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with httpx.Client(base_url=base, timeout=120) as client:
        init = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "e2e", "version": "1"},
                },
            },
        )
        assert init.status_code == 200, init.text
        session = init.headers.get("mcp-session-id")
        if session:
            headers["Mcp-Session-Id"] = session
        client.post(
            "/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        called = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool, "arguments": args},
            },
        )
        assert called.status_code == 200, called.text
        body = _parse(called)
        assert "result" in body, body
        return body["result"]


@pytest.fixture(scope="session")
def mcp_call():  # type: ignore[no-untyped-def]
    """The MCP tool caller."""
    return _mcp_call
