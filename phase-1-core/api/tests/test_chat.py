"""Private chat messages stored by the server, encrypted at rest (beta)."""

import hashlib
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy.exc
from fastapi.testclient import TestClient
from tests.conftest import auth_header, beta, run_sql
from tests.fake_kms import FakeKms
from tests.test_reports import owner_row

from api.auth import issue_token
from api.config import get_settings
from api.main import create_app

Person = tuple[uuid.UUID, str, dict[str, str]]


@pytest.fixture
def kms_arn(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Use a test KMS key."""
    monkeypatch.setenv("USER_KEYS_KMS_ARN", "arn:aws:kms:ap-south-1:000000000000:key/test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_bad_messages_are_422() -> None:
    """Bad messages are 422."""
    client = TestClient(create_app())
    url = f"/conversations/{uuid.uuid4()}/messages"
    agent = {"Authorization": f"Bearer {issue_token(uuid.uuid4(), 'bot', 'agent')}"}
    me = auth_header(uuid.uuid4())
    assert client.post(url, json={"text": "hi"}, headers=agent).status_code == 403
    assert client.get(url, headers=agent).status_code == 403
    for bad in ({}, {"text": "   "}, {"text": "x" * 4001}, {"text": "hi", "extra": 1}):
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
def test_messages_members_only_sealed_and_reportable(people: list[Person], kms_arn: None) -> None:
    """Messages members only sealed and reportable."""
    (_, _, a), (_, bob, bh), (_, _, c) = people
    with TestClient(create_app()) as client:
        client.app.state.kms = FakeKms()  # type: ignore[attr-defined]
        cid = client.post("/conversations/direct", json={"handle": bob}, headers=a).json()["id"]
        url = f"/conversations/{cid}/messages"

        first = client.post(url, json={"text": "hola amigo"}, headers=a)
        assert first.status_code == 201
        hola = first.json()
        assert hola["text"] == "hola amigo" and hola["mine"] is True and hola["kind"] == "text"
        assert client.get(url, headers=bh).status_code == 404
        assert client.get(url, headers=c).status_code == 404
        assert client.post(url, json={"text": "x"}, headers=c).status_code == 404

        client.post(f"/conversations/{cid}/accept", headers=bh)
        seen = client.get(url, headers=bh).json()
        assert [m["text"] for m in seen] == ["hola amigo"] and seen[0]["mine"] is False
        hey = client.post(url, json={"text": "hey, all good?"}, headers=bh).json()
        assert [m["id"] for m in client.get(f"{url}?after={hola['id']}", headers=a).json()] == [
            hey["id"]
        ]

        stored = owner_row(
            "SELECT body_sealed FROM chat_messages WHERE id = :id", {"id": hey["id"]}
        )
        assert stored is not None and b"all good" not in bytes(stored[0])  # type: ignore[arg-type]
        with pytest.raises(sqlalchemy.exc.ProgrammingError, match="permission denied"):
            run_sql("UPDATE chat_messages SET meta = '{}' WHERE id = :id", {"id": hey["id"]})
        with pytest.raises(sqlalchemy.exc.ProgrammingError, match="permission denied"):
            run_sql("DELETE FROM chat_messages WHERE id = :id", {"id": hey["id"]})

        stray = {"text": "see this", "attachment_id": str(uuid.uuid4())}
        assert client.post(url, json=stray, headers=a).status_code == 422

        report = {"reason": "harassment", "message_ids": [hey["id"]]}
        assert (
            client.post(f"/conversations/{cid}/reports", json=report, headers=c).status_code == 404
        )
        made = client.post(f"/conversations/{cid}/reports", json=report, headers=a)
        assert made.status_code == 201
        copy = owner_row(
            "SELECT reported_handle, content->0->>'text' FROM reports WHERE id = :id",
            {"id": made.json()["id"]},
        )
        assert copy == (bob, "hey, all good?")
