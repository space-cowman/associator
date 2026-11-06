"""Private clusters and direct chats: membership, requests, roles and blocking (against beta)."""

import hashlib
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from tests.conftest import auth_header, beta, run_sql

from api.auth import issue_token
from api.main import create_app

Person = tuple[uuid.UUID, str, dict[str, str]]


def test_ai_apps_cannot_use_private_chats() -> None:
    """Ai apps cannot use private chats."""
    agent = {"Authorization": f"Bearer {issue_token(uuid.uuid4(), 'bot', 'agent')}"}
    client = TestClient(create_app())
    assert client.get("/conversations", headers=agent).status_code == 403
    assert client.post("/conversations", json={"name": "x"}, headers=agent).status_code == 403
    assert client.get("/people?q=zz", headers=agent).status_code == 403


def test_bad_input_is_422() -> None:
    """Bad input is 422."""
    me = auth_header(uuid.uuid4())
    client = TestClient(create_app())
    assert client.post("/conversations", json={"name": "  "}, headers=me).status_code == 422
    assert client.post("/conversations", json={"name": "a\nb"}, headers=me).status_code == 422
    assert client.post("/conversations", json={"name": "x" * 61}, headers=me).status_code == 422
    too_many = {"name": "ok", "members": [f"user-{i:03}" for i in range(50)]}
    assert client.post("/conversations", json=too_many, headers=me).status_code == 422
    assert client.get("/people?q=a", headers=me).status_code == 422
    assert client.get("/people?q=a%25", headers=me).status_code == 422


@pytest.fixture
def people() -> Iterator[list[Person]]:
    """Three throwaway people; their chats and blocks are removed afterwards."""
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
    run_sql("DELETE FROM conversations WHERE created_by = ANY(:ids)", {"ids": ids}, as_owner=True)
    run_sql("DELETE FROM users WHERE id = ANY(:ids)", {"ids": ids}, as_owner=True)


@beta
def test_cluster_invite_accept_roles_and_leave(people: list[Person]) -> None:
    """Cluster invite accept roles and leave."""
    (_, alice, a), (_, bob, b), (_, carol, c) = people
    with TestClient(create_app()) as client:
        made = client.post(
            "/conversations", json={"name": "Trip plans", "members": [bob, "zz-nobody"]}, headers=a
        )
        assert made.status_code == 201
        assert made.json()["not_invited"] == ["zz-nobody"]
        cid = made.json()["conversation"]["id"]
        assert made.json()["conversation"]["my_role"] == "admin"

        invite = client.get(f"/conversations/{cid}", headers=b).json()
        assert invite["my_state"] == "invited" and invite["invited_by"] == alice
        assert invite["members"] == []
        assert client.get(f"/conversations/{cid}", headers=c).status_code == 404

        assert (
            client.patch(f"/conversations/{cid}", json={"name": "x"}, headers=b).status_code == 403
        )
        assert client.post(f"/conversations/{cid}/accept", headers=c).status_code == 404

        assert client.post(f"/conversations/{cid}/accept", headers=b).json()["my_state"] == "active"
        detail = client.get(f"/conversations/{cid}", headers=b).json()
        assert detail["member_count"] == 2
        assert {m["handle"] for m in detail["members"]} == {alice, bob}

        body = {"handles": [carol]}
        assert client.post(f"/conversations/{cid}/members", json=body, headers=b).status_code == 403
        assert client.post(f"/conversations/{cid}/members", json=body, headers=a).json() == {
            "not_invited": []
        }
        patched = client.patch(
            f"/conversations/{cid}", json={"name": "Goa trip", "ai_enabled": False}, headers=a
        ).json()
        assert patched["title"] == "Goa trip" and patched["ai_enabled"] is False

        assert client.post(f"/conversations/{cid}/decline", headers=c).status_code == 204
        assert client.get(f"/conversations/{cid}", headers=c).status_code == 404

        assert client.post(f"/conversations/{cid}/leave", headers=a).status_code == 204
        assert client.get(f"/conversations/{cid}", headers=a).status_code == 404
        assert client.get(f"/conversations/{cid}", headers=b).json()["my_role"] == "admin"

        role = client.put(
            f"/conversations/{cid}/members/{bob}/role", json={"role": "member"}, headers=b
        )
        assert role.status_code == 200
        assert client.get(f"/conversations/{cid}", headers=b).json()["my_role"] == "admin"

        client.post(f"/conversations/{cid}/members", json={"handles": [alice]}, headers=b)
        assert client.get(f"/conversations/{cid}", headers=a).json()["my_state"] == "invited"
        assert client.delete(f"/conversations/{cid}/members/{alice}", headers=b).status_code == 204
        assert client.get(f"/conversations/{cid}", headers=a).status_code == 404


@beta
def test_direct_chat_is_a_request_until_accepted(people: list[Person]) -> None:
    """Direct chat is a request until accepted."""
    (_, alice, a), (_, bob, b), _ = people
    with TestClient(create_app()) as client:
        chat = client.post("/conversations/direct", json={"handle": bob}, headers=a)
        assert chat.status_code == 201
        cid = chat.json()["id"]
        assert chat.json()["title"] == f"@{bob}" and chat.json()["my_state"] == "active"

        again = client.post("/conversations/direct", json={"handle": bob}, headers=a).json()
        assert again["id"] == cid
        request = next(x for x in client.get("/conversations", headers=b).json() if x["id"] == cid)
        assert request["my_state"] == "invited" and request["title"] == f"@{alice}"

        assert client.post(f"/conversations/{cid}/accept", headers=b).json()["member_count"] == 2
        assert (
            client.patch(f"/conversations/{cid}", json={"name": "x"}, headers=a).status_code == 403
        )
        assert (
            client.post("/conversations/direct", json={"handle": alice}, headers=a).status_code
            == 404
        )


@beta
def test_blocking(people: list[Person]) -> None:
    """Blocking."""
    (_, alice, a), (_, bob, b), _ = people
    with TestClient(create_app()) as client:
        cid = client.post("/conversations/direct", json={"handle": bob}, headers=a).json()["id"]
        assert client.put(f"/me/blocks/{alice}", headers=b).status_code == 204
        assert client.get(f"/conversations/{cid}", headers=b).status_code == 404
        assert client.get("/me/blocks", headers=b).json() == [alice]

        again = client.post("/conversations/direct", json={"handle": bob}, headers=a)
        assert again.status_code == 404
        made = client.post("/conversations", json={"name": "x", "members": [bob]}, headers=a)
        assert made.json()["not_invited"] == [bob]
        assert bob not in client.get(f"/people?q={bob[:12]}", headers=a).json()
        assert alice not in client.get(f"/people?q={alice[:12]}", headers=b).json()

        assert client.delete(f"/me/blocks/{alice}", headers=b).status_code == 204
        assert client.get(f"/people?q={bob}", headers=a).json() == [bob]
        assert (
            client.post("/conversations/direct", json={"handle": bob}, headers=a).status_code == 201
        )
