"""Profiles, sorting, group membership and notifications (against beta)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from tests.conftest import auth_header, beta, run_sql, use_real_safety

from api.auth import issue_token
from api.main import create_app
from api.routes.signin import TERMS_VERSION


def test_bad_sort_values_are_422() -> None:
    """Bad sort values are 422."""
    client = TestClient(create_app())
    assert client.get("/threads?sort=random").status_code == 422
    assert client.get("/threads?sort=top&window=year").status_code == 422
    assert client.get("/threads?sort=hot&offset=5000").status_code == 422


@pytest.fixture
def two_people(
    beta_user: tuple[uuid.UUID, str],
) -> tuple[tuple[uuid.UUID, str], tuple[uuid.UUID, str]]:
    """Two throwaway people."""
    other = uuid.uuid4()
    handle = f"zz-test-{other.hex[:8]}"
    run_sql(
        "INSERT INTO users (id, handle, auth_provider, provider_user_id_hash)"
        " VALUES (:id, :h, 'dev', :p)",
        {"id": other, "h": handle, "p": other.hex},
    )
    yield beta_user, (other, handle)
    run_sql("DELETE FROM replies WHERE author_id = :u", {"u": other}, as_owner=True)
    run_sql("DELETE FROM users WHERE id = :u", {"u": other}, as_owner=True)


@beta
def test_social_flow(two_people: tuple) -> None:
    """Social flow."""
    (asker_id, asker), (answerer_id, answerer) = two_people
    a, b = auth_header(asker_id, asker), auth_header(answerer_id, answerer)
    with TestClient(create_app()) as client:
        use_real_safety(client.app)  # type: ignore[arg-type]
        try:
            group = client.post(
                "/groups", json={"name": f"zz social {uuid.uuid4().hex[:6]}"}, headers=a
            ).json()
            slug = group["slug"]
            assert group["joined"] is True and group["member_count"] == 1

            assert client.put(f"/groups/{slug}/membership", headers=b).status_code == 204
            assert client.put(f"/groups/{slug}/membership", headers=b).status_code == 204
            seen_by_b = client.get(f"/groups/{slug}", headers=b).json()
            assert seen_by_b["joined"] is True and seen_by_b["member_count"] == 2
            assert client.get(f"/groups/{slug}").json()["joined"] is False
            assert client.delete(f"/groups/{slug}/membership", headers=b).status_code == 204
            assert client.get(f"/groups/{slug}", headers=b).json()["joined"] is False
            assert client.put("/groups/zz-no-such-group/membership", headers=b).status_code == 404

            t = client.post(
                "/threads", json={"group": slug, "text": "Is Rust faster than Go?"}, headers=a
            ).json()
            r = client.post(
                f"/threads/{t['id']}/replies", json={"text": "Often, yes."}, headers=b
            ).json()
            notes = client.get("/me/notifications", headers=a).json()
            assert notes["unread"] >= 1
            first = notes["items"][0]
            assert (first["kind"], first["actor"], first["thread_id"]) == (
                "reply",
                answerer,
                t["id"],
            )

            client.post(f"/threads/{t['id']}/replies", json={"text": "Thanks!"}, headers=a)
            assert client.get("/me/notifications", headers=a).json()["unread"] == notes["unread"]

            client.put(f"/threads/{t['id']}/satisfied", json={"reply_id": r["id"]}, headers=a)
            client.post(f"/replies/{r['id']}/vote", json={"value": 1}, headers=a)
            b_notes = client.get("/me/notifications", headers=b).json()
            assert (
                b_notes["items"][0]["kind"] == "satisfied" and b_notes["items"][0]["actor"] == asker
            )
            profile = client.get(f"/users/{answerer}").json()
            assert (profile["answers"], profile["satisfied"], profile["reputation"]) == (
                1,
                1,
                1 + 5,
            )
            answers = client.get(f"/users/{answerer}/answers").json()
            assert (
                answers[0]["satisfied"] is True
                and answers[0]["thread_text"] == "Is Rust faster than Go?"
            )
            assert [x["id"] for x in client.get(f"/users/{asker}/threads").json()][:1] == [t["id"]]
            assert client.get("/users/zz-nobody-here").status_code == 404

            assert client.post("/me/notifications/read", headers=b).status_code == 204
            assert client.get("/me/notifications", headers=b).json()["unread"] == 0

            for q in (
                "sort=new",
                "sort=top&window=week",
                "sort=hot",
                "sort=top&window=all&offset=0",
            ):
                page = client.get(f"/groups/{slug}/threads?{q}")
                assert page.status_code == 200 and page.json()[0]["id"] == t["id"], q
        finally:
            redis = client.app.state.redis
            for key in ("groups:create", "threads:create", "replies:create", "votes"):
                for uid in (asker_id, answerer_id):
                    client.portal.call(redis.delete, f"ratelimit:{key}:{uid}")


@beta
def test_accepting_updated_terms(beta_user: tuple[uuid.UUID, str]) -> None:
    """Accepting updated terms."""
    user_id, handle = beta_user
    me = auth_header(user_id, handle)
    with TestClient(create_app()) as client:
        run_sql(
            "UPDATE users SET terms_version = '2026-10-27', terms_accepted_at = now()"
            " WHERE id = :id",
            {"id": user_id},
        )
        assert client.get("/me", headers=me).json()["terms_current"] is False
        agent = {"Authorization": f"Bearer {issue_token(user_id, handle, 'agent')}"}
        assert (
            client.post("/me/terms", json={"version": TERMS_VERSION}, headers=agent).status_code
            == 403
        )
        assert (
            client.post("/me/terms", json={"version": "2020-01-01"}, headers=me).status_code == 409
        )
        assert (
            client.post("/me/terms", json={"version": TERMS_VERSION}, headers=me).status_code == 204
        )
        got = client.get("/me", headers=me).json()
        assert got["terms_current"] is True and got["terms_version"] == TERMS_VERSION
