"""The api side of AI apps (MCP)."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from tests.conftest import auth_header, beta, run_sql, use_real_safety

from api.main import create_app

FAKE = "sop_" + "B" * 43  # pragma: allowlist secret


def test_unknown_access_token_is_401() -> None:
    """Unknown access token is 401."""
    r = TestClient(create_app()).get("/me", headers={"Authorization": "Bearer sop_short"})
    assert r.status_code == 401


@pytest.fixture
def setup(beta_user: tuple[uuid.UUID, str]) -> Iterator[tuple[TestClient, dict[str, str], str]]:
    """A test app and a question for AI apps."""
    user_id, handle = beta_user
    group = f"zz-test-{uuid.uuid4().hex[:8]}"
    run_sql(
        "INSERT INTO topic_groups (slug, name, created_by) VALUES (:s, 'Test', :u)",
        {"s": group, "u": user_id},
    )
    with TestClient(create_app()) as client:
        use_real_safety(client.app)  # type: ignore[arg-type]
        yield client, auth_header(user_id, handle), group
        for key in ("tokens", "drafts", "threads:create", "replies:create", "votes"):
            client.portal.call(client.app.state.redis.delete, f"ratelimit:{key}:{user_id}")
    run_sql("DELETE FROM access_tokens WHERE user_id = :u", {"u": user_id}, as_owner=True)


@beta
def test_tokens_shown_once_act_as_agent_and_can_be_revoked(setup: tuple) -> None:
    """Tokens shown once act as agent and can be revoked."""
    client, human, _ = setup
    created = client.post("/me/tokens", json={"name": "claude-code laptop"}, headers=human)
    assert created.status_code == 201
    token = created.json()["token"]
    assert token.startswith("sop_") and len(token) == 47
    listed = client.get("/me/tokens", headers=human).json()
    assert listed[0]["token_last4"] == token[-4:] and "token" not in listed[0]

    agent = {"Authorization": f"Bearer {token}"}
    assert client.get("/me", headers=agent).status_code == 200
    assert client.post("/me/tokens", json={"name": "x"}, headers=agent).status_code == 403
    assert client.get("/me/tokens", headers=agent).status_code == 403
    assert client.post(f"/drafts/{uuid.uuid4()}/approve", json={}, headers=agent).status_code == 403

    assert client.get("/me", headers={"Authorization": f"Bearer {FAKE}"}).status_code == 401
    assert client.delete(f"/me/tokens/{listed[0]['id']}", headers=human).status_code == 204
    assert client.get("/me", headers=agent).status_code == 401


@beta
def test_agent_question_label_and_author_deletion(setup: tuple) -> None:
    """Agent question label and author deletion."""
    client, human, group = setup
    token = client.post("/me/tokens", json={"name": "test"}, headers=human).json()["token"]
    agent = {"Authorization": f"Bearer {token}"}
    marker = uuid.uuid4().hex[:10]

    posted = client.post(
        "/threads",
        headers=agent,
        json={"group": group, "text": f"{marker} why does my pod restart?"},
    )
    assert posted.status_code == 201 and posted.json()["by_agent"] is True
    tid = posted.json()["id"]
    mine = client.post(
        "/threads",
        headers=human,
        json={"group": group, "text": f"{marker} written by me"},
    )
    assert mine.json()["by_agent"] is False

    assert client.delete(f"/threads/{tid}", headers=agent).status_code == 403
    assert client.delete(f"/threads/{tid}", headers=auth_header(uuid.uuid4())).status_code == 404
    assert client.delete(f"/threads/{tid}", headers=human).status_code == 204
    assert client.get(f"/threads/{tid}").status_code == 404
    assert tid not in [t["id"] for t in client.get(f"/groups/{group}/threads").json()]
    found = client.post("/threads/search-similar", json={"text": f"{marker} pod restart"}).json()
    assert tid not in [t["id"] for t in found]
    assert (
        client.post(f"/threads/{tid}/replies", json={"text": "hi"}, headers=human).status_code
        == 404
    )


@beta
def test_answers_from_an_ai_app_wait_for_approval(setup: tuple) -> None:
    """Answers from an ai app wait for approval."""
    client, human, group = setup
    token = client.post("/me/tokens", json={"name": "test"}, headers=human).json()["token"]
    agent = {"Authorization": f"Bearer {token}"}
    tid = client.post(
        "/threads",
        headers=human,
        json={"group": group, "text": "Postgres or MySQL?"},
    ).json()["id"]

    body = {
        "text": "Postgres, for JSON support.",
        "idempotency_key": "mcp-test-0001",
        "model_label": "Claude",
    }
    assert client.post(f"/threads/{tid}/agent-drafts", json=body, headers=human).status_code == 403
    draft = client.post(f"/threads/{tid}/agent-drafts", json=body, headers=agent)
    assert draft.status_code == 201
    d = draft.json()
    assert (d["status"], d["mode"], d["model_label"]) == ("pending", "mcp", "Claude")
    again = client.post(f"/threads/{tid}/agent-drafts", json=body, headers=agent)
    assert again.json()["id"] == d["id"]
    leak = {
        **body,
        "idempotency_key": "mcp-test-0002",
        "text": "export DB_PASSWORD=s3cr3tPass99",
    }  # pragma: allowlist secret
    assert client.post(f"/threads/{tid}/agent-drafts", json=leak, headers=agent).status_code == 422

    assert client.get(f"/threads/{tid}/replies").json() == []
    assert client.post(f"/drafts/{d['id']}/approve", json={}, headers=agent).status_code == 403
    assert client.post(f"/drafts/{d['id']}/approve", json={}, headers=human).status_code == 200
    (reply,) = client.get(f"/threads/{tid}/replies").json()
    assert reply["by_agent"] is True and reply["text"] == "Postgres, for JSON support."
