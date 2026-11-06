import uuid

import pytest
from fastapi.testclient import TestClient
from tests.conftest import auth_header, beta, run_sql

from api.auth import issue_token
from api.main import create_app


def test_vote_on_question_needs_sign_in_and_valid_value() -> None:
    """Vote on question needs sign in and valid value."""
    client = TestClient(create_app())
    assert client.post(f"/threads/{uuid.uuid4()}/vote", json={"value": 1}).status_code == 401
    r = client.post(
        f"/threads/{uuid.uuid4()}/vote", json={"value": 5}, headers=auth_header(uuid.uuid4())
    )
    assert r.status_code == 422


@pytest.fixture
def thread(beta_user: tuple[uuid.UUID, str]) -> str:
    """A throwaway question."""
    user_id = beta_user[0]
    slug, tid = f"zz-test-{uuid.uuid4().hex[:8]}", str(uuid.uuid4())
    run_sql(
        "INSERT INTO topic_groups (slug, name, description, created_by)"
        " VALUES (:s, 'Test', 'A test group', :u)",
        {"s": slug, "u": user_id},
    )
    run_sql(
        "INSERT INTO threads (id, group_id, author_id, text)"
        " SELECT :t, id, :u, 'feed test' FROM topic_groups WHERE slug = :s",
        {"t": tid, "u": user_id, "s": slug},
    )
    return tid


@beta
def test_feed_counts_and_question_votes(beta_user: tuple[uuid.UUID, str], thread: str) -> None:
    """Feed counts and question votes."""
    author_id, handle = beta_user
    voter = uuid.uuid4()
    run_sql(
        "INSERT INTO users (id, handle, auth_provider, provider_user_id_hash)"
        " VALUES (:id, :h, 'dev', :p)",
        {"id": voter, "h": f"zz-test-{voter.hex[:8]}", "p": voter.hex},
    )
    human = auth_header(voter)
    agent = {"Authorization": f"Bearer {issue_token(voter, 'v', 'agent')}"}
    with TestClient(create_app()) as client:
        try:
            feed = client.get("/threads?limit=50").json()
            card = next(t for t in feed if t["id"] == thread)
            assert card["reply_count"] == 0 and card["votes"]["human"] == {"up": 0, "down": 0}

            client.post(f"/threads/{thread}/vote", json={"value": 1}, headers=human)
            counts = client.post(f"/threads/{thread}/vote", json={"value": 1}, headers=agent).json()
            assert counts == {"human": {"up": 1, "down": 0}, "agent": {"up": 1, "down": 0}}
            flipped = client.post(
                f"/threads/{thread}/vote", json={"value": -1}, headers=human
            ).json()
            assert flipped["human"] == {"up": 0, "down": 1}

            own = client.post(
                f"/threads/{thread}/vote", json={"value": 1}, headers=auth_header(author_id, handle)
            )
            assert own.status_code == 403
            assert (
                client.post(
                    f"/threads/{uuid.uuid4()}/vote", json={"value": 1}, headers=human
                ).status_code
                == 404
            )

            run_sql(
                "INSERT INTO replies (thread_id, author_id, text, mode)"
                " VALUES (:t, :u, 'an answer', 'self')",
                {"t": thread, "u": voter},
            )
            detail = client.get(f"/threads/{thread}").json()
            assert detail["reply_count"] == 1 and detail["votes"]["agent"]["up"] == 1
            groups = {g["slug"]: g for g in client.get("/groups").json()}
            assert any(g["description"] == "A test group" for g in groups.values())
        finally:
            client.portal.call(client.app.state.redis.delete, f"ratelimit:votes:{voter}")
            run_sql("DELETE FROM users WHERE id = :u", {"u": voter}, as_owner=True)
