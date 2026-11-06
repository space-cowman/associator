"""Memory: split, encryption, search; import/edit/delete against beta (fake KMS + gateway)."""

import json
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import psycopg
import pytest
from cryptography.exceptions import InvalidTag
from fastapi.testclient import TestClient
from tests.conftest import auth_header, beta, run_sql, use_real_safety
from tests.fake_kms import FakeKms

from api import memory
from api.auth import CurrentUser, issue_token
from api.config import get_settings
from api.main import create_app


def test_split_lines_bullets_long_lines_and_repeats() -> None:
    """Split lines bullets long lines and repeats."""
    long = "I like tea. " * 40
    items = memory.split(f"- I live in Pune\n\n* I use a Mac (arm64)\n• I live in Pune\n{long}")
    assert items[:2] == ["I live in Pune", "I use a Mac (arm64)"]
    assert items[2:] == ["I like tea."]
    assert all(len(i) <= memory.ITEM_CHARS for i in memory.split("word " * 200))


def test_seal_binds_the_item_and_part() -> None:
    """Seal binds the item and part."""
    key, a, b = bytes(32), uuid.uuid4(), uuid.uuid4()
    blob = memory.seal(key, a, "text", b"I live in Pune")
    assert b"Pune" not in blob and memory.unseal(key, a, "text", blob) == b"I live in Pune"
    for other_id, part in ((b, "text"), (a, "vec")):
        with pytest.raises(InvalidTag):
            memory.unseal(key, other_id, part, blob)
    assert memory.unpack(memory.pack([0.5, -1.0, 2.0])) == [0.5, -1.0, 2.0]


def _item(text: str, vector: list[float] | None = None) -> memory.Item:
    """A memory item for tests."""
    now = datetime.now(UTC)
    return memory.Item(uuid.uuid4(), text, vector, "m" if vector else None, now, now)


def test_rank_by_vectors_then_keywords() -> None:
    """Rank by vectors then keywords."""
    mac, pune = _item("I use a Mac", [1.0, 0.0]), _item("I live in Pune", [0.0, 1.0])
    assert memory.rank([mac, pune], "laptop?", ("m", [0.9, 0.1]), 5) == [mac]
    assert memory.rank([mac, pune], "Where in Pune?", ("other", [1.0, 0.0]), 5) == [pune]
    assert memory.rank([mac, pune], "nothing related", None, 5) == []


SECRET = "sk-proj-" + "Ab3dE6gH" * 6  # pragma: allowlist secret


def _vector(text: str) -> list[float]:
    """A tiny test vector for a text."""
    low = text.lower()
    return [float("mac" in low or "laptop" in low), float("pune" in low), 0.1]


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, list[dict[str, Any]]]]:
    """A test app with fake KMS and gateway."""
    monkeypatch.setenv("USER_KEYS_KMS_ARN", "arn:aws:kms:ap-south-1:000000000000:key/test")
    get_settings.cache_clear()
    sent: list[dict[str, Any]] = []

    def gateway(request: httpx.Request) -> httpx.Response:
        """Answer embedding requests with test vectors."""
        body = json.loads(request.content)
        sent.append(body)
        vectors = [_vector(t) for t in body["texts"]]
        return httpx.Response(200, json={"model": "text-embedding-3-small", "vectors": vectors})

    with TestClient(create_app()) as client:
        client.app.state.kms = FakeKms()  # type: ignore[attr-defined]
        client.app.state.gateway = httpx.AsyncClient(  # type: ignore[attr-defined]
            transport=httpx.MockTransport(gateway), base_url="http://gw"
        )
        use_real_safety(client.app)  # type: ignore[arg-type]
        yield client, sent
    get_settings.cache_clear()


def _raw_text(user_id: uuid.UUID) -> bytes:
    """What the database holds, read as the owner (proves nothing readable is stored)."""
    with psycopg.connect(
        host="127.0.0.1",
        port=15432,
        dbname="platform_v2",
        user="platform_v2_owner",
        password=os.environ["TEST_OWNER_PASSWORD"],
    ) as conn:
        rows = conn.execute(
            "SELECT text_ct, coalesce(vec_ct, '') FROM memory_items WHERE user_id = %s",
            (user_id,),
        ).fetchall()
    return b"".join(bytes(a) + bytes(b) for a, b in rows)


@beta
def test_import_list_edit_delete_keywords_only(
    app: tuple[TestClient, list[dict[str, Any]]], beta_user: tuple[uuid.UUID, str]
) -> None:
    """Import list edit delete keywords only."""
    client, sent = app
    user_id, handle = beta_user
    me = auth_header(user_id, handle)
    try:
        made = client.post(
            "/me/memory/import", json={"text": "I live in Pune\nI use a Mac"}, headers=me
        )
        assert made.status_code == 201, made.text
        assert [i["text"] for i in made.json()] == ["I live in Pune", "I use a Mac"]
        assert not any(i["searchable"] for i in made.json()) and sent == []
        raw = _raw_text(user_id)
        assert b"Pune" not in raw and b"Mac" not in raw

        first = made.json()[0]["id"]
        edited = client.patch(f"/me/memory/{first}", json={"text": "I live in Mumbai"}, headers=me)
        assert edited.status_code == 200 and edited.json()["text"] == "I live in Mumbai"
        listed = client.get("/me/memory", headers=me).json()
        assert [i["text"] for i in listed] == ["I live in Mumbai", "I use a Mac"]

        blocked = client.post("/me/memory/import", json={"text": f"my key {SECRET}"}, headers=me)
        assert blocked.status_code == 422 and SECRET not in blocked.text
        assert len(client.get("/me/memory", headers=me).json()) == 2
        stranger = auth_header(uuid.uuid4())
        assert (
            client.patch(f"/me/memory/{first}", json={"text": "x"}, headers=stranger).status_code
            == 404
        )
        assert client.delete(f"/me/memory/{first}", headers=stranger).status_code == 404
        agent = {"Authorization": f"Bearer {issue_token(user_id, handle, 'agent')}"}
        assert client.get("/me/memory", headers=agent).status_code == 403

        too_many = "\n".join(f"fact number {n}" for n in range(memory.MAX_ITEMS))
        assert (
            client.post("/me/memory/import", json={"text": too_many}, headers=me).status_code == 422
        )

        assert client.delete(f"/me/memory/{first}", headers=me).status_code == 204
        assert len(client.get("/me/memory", headers=me).json()) == 1
        assert client.delete("/me/memory", headers=me).status_code == 204
        assert client.get("/me/memory", headers=me).json() == []
    finally:
        client.portal.call(client.app.state.redis.delete, f"ratelimit:memory:{user_id}")  # type: ignore[attr-defined]
        run_sql("DELETE FROM memory_items WHERE user_id = :u", {"u": user_id}, as_owner=True)
        run_sql("DELETE FROM memory_keys WHERE user_id = :u", {"u": user_id}, as_owner=True)


@beta
def test_vectors_with_the_persons_own_provider(
    app: tuple[TestClient, list[dict[str, Any]]], beta_user: tuple[uuid.UUID, str]
) -> None:
    """Vectors with the persons own provider."""
    client, sent = app
    user_id, handle = beta_user
    me = auth_header(user_id, handle)
    model_id = uuid.uuid4()
    run_sql(
        "INSERT INTO model_registry (id, user_id, provider, model_name, key_ciphertext, key_last4)"
        " VALUES (:id, :u, 'openai', 'gpt-5-mini', :ct, 'ab12')",
        {"id": model_id, "u": user_id, "ct": b"\x01\x02ciphertext-bytes"},
    )
    try:
        made = client.post(
            "/me/memory/import", json={"text": "I live in Pune\nI use a Mac"}, headers=me
        )
        assert made.status_code == 201 and all(i["searchable"] for i in made.json())
        assert sent[-1]["user_model"]["model_id"] == str(model_id)

        found = client.portal.call(
            memory.retrieve,
            _request(client),
            CurrentUser(id=user_id, handle=handle, actor="human"),
            "which laptop do I use?",
        )
        assert [i.text for i in found] == ["I use a Mac"]
    finally:
        client.portal.call(client.app.state.redis.delete, f"ratelimit:memory:{user_id}")  # type: ignore[attr-defined]
        run_sql("DELETE FROM memory_items WHERE user_id = :u", {"u": user_id}, as_owner=True)
        run_sql("DELETE FROM memory_keys WHERE user_id = :u", {"u": user_id}, as_owner=True)
        run_sql("DELETE FROM model_registry WHERE id = :id", {"id": model_id}, as_owner=True)


def _request(client: TestClient) -> Any:
    """A minimal stand-in for a Request: memory only reads request.app.state."""

    class _R:
        app = client.app

    return _R()
