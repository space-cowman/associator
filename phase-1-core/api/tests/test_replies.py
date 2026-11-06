import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from tests.conftest import auth_header, beta, run_sql, use_real_safety

from api.main import create_app
from api.routes.replies import MAX_DEPTH

THREAD = uuid.uuid4()


def test_reply_needs_sign_in() -> None:
    """Reply needs sign in."""
    response = TestClient(create_app()).post(f"/threads/{THREAD}/replies", json={"text": "hi"})
    assert response.status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"text": ""},
        {"text": "x" * 501},
        {"text": "see ‮gnp.exe"},
        {"text": "esc \x1b char"},
        {"text": "hi", "mode": "ask_my_ai"},
        {"text": "hi", "human_approved": True},
        {"text": "hi", "author_id": str(uuid.uuid4())},
        {"text": "hi", "depth": 0},
        {"text": "hi", "parent_id": "not-a-uuid"},
    ],
)
def test_bad_reply_is_422(body: dict[str, object]) -> None:
    """Bad reply is 422."""
    response = TestClient(create_app()).post(
        f"/threads/{THREAD}/replies", json=body, headers=auth_header(uuid.uuid4())
    )
    assert response.status_code == 422


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "after=nope"])
def test_bad_list_query_is_422(query: str) -> None:
    """Bad list query is 422."""
    assert TestClient(create_app()).get(f"/threads/{THREAD}/replies?{query}").status_code == 422


@pytest.fixture
def two_threads(beta_user: tuple[uuid.UUID, str]) -> tuple[str, str]:
    """Two throwaway questions."""
    user_id = beta_user[0]
    slug = f"zz-test-{uuid.uuid4().hex[:8]}"
    run_sql(
        "INSERT INTO topic_groups (slug, name, created_by) VALUES (:s, 'Test', :u)",
        {"s": slug, "u": user_id},
    )
    ids = (str(uuid.uuid4()), str(uuid.uuid4()))
    for thread_id in ids:
        run_sql(
            "INSERT INTO threads (id, group_id, author_id, text)"
            " SELECT :t, id, :u, 'test thread' FROM topic_groups WHERE slug = :s",
            {"t": thread_id, "u": user_id, "s": slug},
        )
    return ids


@beta
def test_reply_nesting_and_paging(
    beta_user: tuple[uuid.UUID, str], two_threads: tuple[str, str]
) -> None:
    """Reply nesting and paging."""
    user_id, handle = beta_user
    headers = auth_header(user_id, handle)
    thread, other_thread = two_threads
    with TestClient(create_app()) as client:
        use_real_safety(client.app)  # type: ignore[arg-type]

        def reply(text: str, parent: str | None = None, on: str = thread) -> httpx.Response:
            return client.post(
                f"/threads/{on}/replies", json={"text": text, "parent_id": parent}, headers=headers
            )

        try:
            top = reply("top-level answer")
            assert top.status_code == 201
            top_json = top.json()
            assert (top_json["depth"], top_json["author"], top_json["by_agent"]) == (
                0,
                handle,
                False,
            )
            for private in ("mode", "model_label", "memory_used", "instruction_given"):
                assert private not in top_json
            assert top_json["reply_to_id"] is None and top_json["reply_to_author"] is None

            nested = reply("nested answer", top_json["id"]).json()
            assert nested["depth"] == 1 and nested["parent_id"] == top_json["id"]

            assert reply("x", top_json["id"], on=other_thread).status_code == 404
            assert reply("x", on=str(uuid.uuid4())).status_code == 404
            assert reply("x", str(uuid.uuid4())).status_code == 404

            deep_id = str(uuid.uuid4())
            run_sql(
                "INSERT INTO replies (id, thread_id, author_id, text, mode, depth)"
                " VALUES (:id, :t, :u, 'seeded deep reply', 'self', :d)",
                {"id": deep_id, "t": thread, "u": user_id, "d": MAX_DEPTH - 1},
            )
            at_limit = reply("at the limit", deep_id).json()
            assert at_limit["depth"] == MAX_DEPTH and at_limit["reply_to_id"] is None

            flat = reply("past the limit", at_limit["id"])
            assert flat.status_code == 201
            flat_json = flat.json()
            assert flat_json["depth"] == MAX_DEPTH
            assert flat_json["parent_id"] == deep_id
            assert flat_json["reply_to_id"] == at_limit["id"]
            assert flat_json["reply_to_author"] == handle

            seen: list[str] = []
            after = ""
            while True:
                page = client.get(f"/threads/{thread}/replies?limit=2{after}").json()
                if not page:
                    break
                seen += [r["id"] for r in page]
                after = f"&after={page[-1]['id']}"
            expected = [top_json["id"], nested["id"], deep_id, at_limit["id"], flat_json["id"]]
            assert seen == expected
        finally:
            client.portal.call(client.app.state.redis.delete, f"ratelimit:replies:create:{user_id}")
