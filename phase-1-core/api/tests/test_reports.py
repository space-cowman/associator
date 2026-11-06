"""Reports: the app can never read reports back (beta)."""

import asyncio
import hashlib
import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from tests.conftest import auth_header, beta, run_sql, use_real_safety

from api.config import get_settings
from api.main import create_app

Person = tuple[uuid.UUID, str, dict[str, str]]


def owner_row(statement: str, params: dict[str, object]) -> tuple[object, ...] | None:
    """Read as the owner role (moderation), which the app role cannot do."""
    url = get_settings().database_url.replace("platform_v2_app@", "platform_v2_owner@")

    async def run() -> tuple[object, ...] | None:
        """Run the query."""
        engine = create_async_engine(
            url, connect_args={"password": os.environ["TEST_OWNER_PASSWORD"]}
        )
        try:
            async with engine.connect() as conn:
                row = (await conn.execute(text(statement), params)).one_or_none()
                return tuple(row) if row else None
        finally:
            await engine.dispose()

    return asyncio.run(run())


def test_bad_reports_are_422() -> None:
    """Bad reports are 422."""
    client = TestClient(create_app())
    url = f"/conversations/{uuid.uuid4()}/reports"
    me = auth_header(uuid.uuid4())
    for bad in (
        {"reason": "spam", "message_ids": []},
        {"reason": "boring", "message_ids": [1]},
        {"reason": "spam", "message_ids": list(range(21))},
        {"reason": "spam", "messages": [{"sender": "ana-x", "text": "hi"}]},
    ):
        assert client.post(url, json=bad, headers=me).status_code == 422


@pytest.fixture
def people() -> Iterator[list[Person]]:
    """Three throwaway people, removed afterwards."""
    made: list[Person] = []
    for _ in range(3):
        uid = uuid.uuid4()
        handle = f"zz-test-{uid.hex[:8]}"
        run_sql(
            "INSERT INTO users (id, handle, auth_provider, provider_user_id_hash)"
            " VALUES (:id, :h, 'dev', :p)",
            {"id": uid, "h": handle, "p": hashlib.sha256(handle.encode()).hexdigest()},
        )
        made.append((uid, handle, auth_header(uid, handle)))
    yield made
    ids = [p[0] for p in made]
    run_sql("DELETE FROM reports WHERE reporter_id = ANY(:ids)", {"ids": ids}, as_owner=True)
    run_sql("DELETE FROM conversations WHERE created_by = ANY(:ids)", {"ids": ids}, as_owner=True)
    run_sql("DELETE FROM users WHERE id = ANY(:ids)", {"ids": ids}, as_owner=True)


@beta
def test_reporting_public_posts(people: list[Person]) -> None:
    """Reporting public posts."""
    (uid_a, _, a), (_, bob, bh), (_, _, c) = people
    with TestClient(create_app()) as client:
        use_real_safety(client.app)  # type: ignore[arg-type]
        slug = client.post(
            "/groups", json={"name": f"zz reports {uuid.uuid4().hex[:6]}"}, headers=a
        ).json()["slug"]
        try:
            t = client.post(
                "/threads", json={"group": slug, "text": "Is this spam? Buy cheap keys"}, headers=a
            ).json()
            r = client.post(
                f"/threads/{t['id']}/replies", json={"text": "Rude reply here."}, headers=bh
            ).json()
            body = {"reason": "spam", "details": "selling keys"}

            made = client.post(f"/threads/{t['id']}/report", json=body, headers=c)
            assert made.status_code == 201
            again = client.post(f"/threads/{t['id']}/report", json=body, headers=c)
            assert again.status_code == 409
            own = client.post(f"/threads/{t['id']}/report", json=body, headers=a)
            assert own.status_code == 409
            rep = client.post(
                f"/replies/{r['id']}/report", json={"reason": "harassment"}, headers=c
            )
            assert rep.status_code == 201
            assert (
                client.post(f"/threads/{uuid.uuid4()}/report", json=body, headers=c).status_code
                == 404
            )

            stored = owner_row(
                "SELECT reason, reported_handle, content->0->>'text' FROM reports WHERE id = :id",
                {"id": made.json()["id"]},
            )
            assert stored == (
                "spam",
                people[0][1],
                "Is this spam? Buy cheap keys",
            )
            stored_reply = owner_row(
                "SELECT thread_id, reply_id FROM reports WHERE id = :id", {"id": rep.json()["id"]}
            )
            assert stored_reply is not None and str(stored_reply[1]) == r["id"]
        finally:
            run_sql(
                "DELETE FROM reports WHERE reporter_id = :u", {"u": people[2][0]}, as_owner=True
            )
            run_sql("DELETE FROM replies WHERE thread_id = :t", {"t": t["id"]}, as_owner=True)
            run_sql(
                "DELETE FROM threads"
                " WHERE group_id = (SELECT id FROM topic_groups WHERE slug = :s)",
                {"s": slug},
                as_owner=True,
            )
            run_sql("DELETE FROM topic_groups WHERE slug = :s", {"s": slug}, as_owner=True)
            assert uid_a
