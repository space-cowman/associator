import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from tests.conftest import auth_header, beta, run_sql, use_real_safety

from api.config import get_settings
from api.main import create_app
from api.similar import find_similar

GOOD = {"group": "devops", "text": "Why does my pod restart?"}


def test_create_needs_sign_in() -> None:
    """Create needs sign in."""
    assert TestClient(create_app()).post("/threads", json=GOOD).status_code == 401


@pytest.mark.parametrize(
    "override",
    [
        {"text": ""},
        {"text": "   \n  "},
        {"text": "x" * 501},
        {"text": "see file ‮gnp.exe"},
        {"text": "bell \x07 char"},
        {"author_id": str(uuid.uuid4())},
        {"group": "Not A Slug"},
        {"text": 123},
    ],
)
def test_bad_thread_is_422(override: dict[str, object]) -> None:
    """Bad thread is 422."""
    response = TestClient(create_app()).post(
        "/threads", json={**GOOD, **override}, headers=auth_header(uuid.uuid4())
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "body",
    [{"text": ""}, {"text": "x" * 501}, {"text": "ok", "limit": 0}, {"text": "ok", "limit": 11}],
)
def test_bad_search_is_422(body: dict[str, object]) -> None:
    """Bad search is 422."""
    assert TestClient(create_app()).post("/threads/search-similar", json=body).status_code == 422


def test_malformed_thread_id_is_422() -> None:
    """Malformed thread id is 422."""
    assert TestClient(create_app()).get("/threads/not-a-uuid").status_code == 422


@pytest.fixture
def beta_group(beta_user: tuple[uuid.UUID, str]) -> str:
    """A throwaway cluster."""
    slug = f"zz-test-{uuid.uuid4().hex[:8]}"
    run_sql(
        "INSERT INTO topic_groups (slug, name, created_by) VALUES (:s, 'Test', :u)",
        {"s": slug, "u": beta_user[0]},
    )
    return slug


@beta
def test_create_read_page_and_search(beta_user: tuple[uuid.UUID, str], beta_group: str) -> None:
    """Create read page and search."""
    user_id, handle = beta_user
    headers = auth_header(user_id, handle)
    marker = uuid.uuid4().hex[:10]
    texts = [
        f"{marker} My pod crashes when I deploy it to k3s",
        f"{marker} Which database for a side project?\nPostgres or MySQL? 👩‍💻",
        f"{marker} Showcase: a CLI that tidies terraform plans",
    ]
    with TestClient(create_app()) as client:
        use_real_safety(client.app)  # type: ignore[arg-type]
        try:
            created = [
                client.post(
                    "/threads",
                    json={"group": beta_group, "text": t},
                    headers=headers,
                )
                for t in texts
            ]
            assert [r.status_code for r in created] == [201, 201, 201]
            first = created[0].json()
            assert first["author"] == handle and first["satisfied_reply_id"] is None
            assert "\n" in created[1].json()["text"]

            read = client.get(f"/threads/{first['id']}")
            assert read.status_code == 200 and read.json() == first

            assert client.get(f"/threads/{uuid.uuid4()}").status_code == 404
            missing = client.post(
                "/threads", json={**GOOD, "group": "zz-no-such-group"}, headers=headers
            )
            assert missing.status_code == 404

            page1 = client.get(f"/groups/{beta_group}/threads?limit=2").json()
            page2 = client.get(
                f"/groups/{beta_group}/threads?limit=2&before={page1[-1]['id']}"
            ).json()
            ids = [t["id"] for t in page1 + page2]
            assert ids == [r.json()["id"] for r in reversed(created)]

            found = client.post(
                "/threads/search-similar", json={"text": f"{marker} pods crashing after deploying"}
            ).json()
            assert found[0]["id"] == first["id"]
            assert set(found[0]) == {"id", "group", "text", "answered"}

            weird = client.post(
                "/threads/search-similar", json={"text": "a & b | !c :* ' ( ) <-> \\"}
            )
            assert weird.status_code == 200
        finally:
            client.portal.call(client.app.state.redis.delete, f"ratelimit:threads:create:{user_id}")

    async def retrieval() -> None:
        """Search that returns nothing."""
        engine = create_async_engine(get_settings().database_url)
        try:
            async with engine.connect() as conn:
                query = f"{marker} pod crash deploy"
                excluded = await find_similar(conn, query, exclude_id=uuid.UUID(first["id"]))
                assert first["id"] not in [str(f.id) for f in excluded]
                answered = await find_similar(conn, query, answered_only=True)
                assert first["id"] not in [str(f.id) for f in answered]
        finally:
            await engine.dispose()

    asyncio.run(retrieval())
