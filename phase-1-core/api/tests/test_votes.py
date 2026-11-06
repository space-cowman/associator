import hashlib
import uuid
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from tests.conftest import auth_header, beta, run_sql, use_real_safety

from api.auth import issue_token
from api.main import create_app

ID = uuid.uuid4()


def test_vote_needs_sign_in() -> None:
    """Vote needs sign in."""
    assert (
        TestClient(create_app()).post(f"/replies/{ID}/vote", json={"value": 1}).status_code == 401
    )


@pytest.mark.parametrize(
    "body",
    [{"value": 2}, {"value": "1"}, {}, {"value": 1, "voter_type": "agent"}],
)
def test_bad_vote_is_422(body: dict[str, object]) -> None:
    """Bad vote is 422."""
    response = TestClient(create_app()).post(
        f"/replies/{ID}/vote", json=body, headers=auth_header(uuid.uuid4())
    )
    assert response.status_code == 422


def test_agent_cannot_mark_satisfied() -> None:
    """Agent cannot mark satisfied."""
    agent = {"Authorization": f"Bearer {issue_token(uuid.uuid4(), 'bot', 'agent')}"}
    response = TestClient(create_app()).put(
        f"/threads/{ID}/satisfied", json={"reply_id": str(ID)}, headers=agent
    )
    assert response.status_code == 403


@pytest.fixture
def people() -> Iterator[dict[str, uuid.UUID]]:
    """asker, answerer, two voters; a group, two threads and a reply each."""
    ids = {name: uuid.uuid4() for name in ("asker", "answerer", "voter1", "voter2")}
    for name, uid in ids.items():
        handle = f"zz-test-{name}-{uid.hex[:6]}"
        run_sql(
            "INSERT INTO users (id, handle, auth_provider, provider_user_id_hash)"
            " VALUES (:id, :h, 'dev', :p)",
            {"id": uid, "h": handle, "p": hashlib.sha256(handle.encode()).hexdigest()},
        )
    ids["group"], ids["thread"], ids["other_thread"] = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ids["reply"], ids["other_reply"], ids["own_reply"] = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    run_sql(
        "INSERT INTO topic_groups (id, slug, name) VALUES (:g, :s, 'Test')",
        {"g": ids["group"], "s": f"zz-test-{ids['group'].hex[:8]}"},
        as_owner=True,
    )
    for thread in ("thread", "other_thread"):
        run_sql(
            "INSERT INTO threads (id, group_id, author_id, text)"
            " VALUES (:t, :g, :a, 'test thread')",
            {"t": ids[thread], "g": ids["group"], "a": ids["asker"]},
        )
    for reply, thread, author in (
        ("reply", "thread", "answerer"),
        ("other_reply", "other_thread", "answerer"),
        ("own_reply", "thread", "asker"),
    ):
        run_sql(
            "INSERT INTO replies (id, thread_id, author_id, text, mode)"
            " VALUES (:r, :t, :a, 'an answer', 'self')",
            {"r": ids[reply], "t": ids[thread], "a": ids[author]},
        )
    yield ids
    run_sql("DELETE FROM threads WHERE group_id = :g", {"g": ids["group"]}, as_owner=True)
    run_sql("DELETE FROM topic_groups WHERE id = :g", {"g": ids["group"]}, as_owner=True)
    for name in ("asker", "answerer", "voter1", "voter2"):
        run_sql("DELETE FROM users WHERE id = :u", {"u": ids[name]}, as_owner=True)


@beta
def test_votes_and_satisfied(people: dict[str, uuid.UUID]) -> None:
    """Votes and satisfied."""
    human = {n: auth_header(people[n], n) for n in ("asker", "answerer", "voter1", "voter2")}
    agent1 = {"Authorization": f"Bearer {issue_token(people['voter1'], 'voter1', 'agent')}"}
    reply, thread = people["reply"], people["thread"]
    with TestClient(create_app()) as client:
        use_real_safety(client.app)  # type: ignore[arg-type]

        def vote(headers: dict[str, str], value: int, on: uuid.UUID = reply) -> httpx.Response:
            return client.post(f"/replies/{on}/vote", json={"value": value}, headers=headers)

        def satisfied(headers: dict[str, str], reply_id: uuid.UUID | None) -> httpx.Response:
            body = {"reply_id": str(reply_id) if reply_id else None}
            return client.put(f"/threads/{thread}/satisfied", json=body, headers=headers)

        try:
            vote(human["voter1"], 1)
            vote(human["voter2"], 1)
            counts = vote(agent1, 1).json()
            assert counts == {"human": {"up": 2, "down": 0}, "agent": {"up": 1, "down": 0}}

            flipped = vote(human["voter2"], -1).json()
            assert flipped["human"] == {"up": 1, "down": 1}
            removed = vote(human["voter2"], 0).json()
            assert removed["human"] == {"up": 1, "down": 0}

            listed = client.get(f"/threads/{thread}/replies").json()
            mine = next(r for r in listed if r["id"] == str(reply))
            assert mine["votes"] == {"human": {"up": 1, "down": 0}, "agent": {"up": 1, "down": 0}}

            assert vote(human["answerer"], 1).status_code == 403
            own_agent = {"Authorization": f"Bearer {issue_token(people['answerer'], 'a', 'agent')}"}
            assert vote(own_agent, 1).status_code == 403
            assert vote(human["voter1"], 1, uuid.uuid4()).status_code == 404

            assert satisfied(human["voter1"], reply).status_code == 403
            ok = satisfied(human["asker"], reply)
            assert ok.status_code == 200
            assert client.get(f"/threads/{thread}").json()["satisfied_reply_id"] == str(reply)

            assert satisfied(human["asker"], people["other_reply"]).status_code == 404
            assert satisfied(human["asker"], people["own_reply"]).status_code == 422
            assert satisfied(human["asker"], None).status_code == 200
            assert client.get(f"/threads/{thread}").json()["satisfied_reply_id"] is None
        finally:
            for name in ("asker", "answerer", "voter1", "voter2"):
                client.portal.call(client.app.state.redis.delete, f"ratelimit:votes:{people[name]}")
