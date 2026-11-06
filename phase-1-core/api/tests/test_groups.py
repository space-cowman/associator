import uuid

import pytest
from fastapi.testclient import TestClient
from tests.conftest import auth_header as _auth
from tests.conftest import beta

from api.main import create_app
from api.routes.groups import CREATE_LIMIT, slug_from


def test_create_needs_sign_in() -> None:
    """Create needs sign in."""
    response = TestClient(create_app()).post("/groups", json={"name": "DevOps"})
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("DevOps", "devops"),
        ("DevOps Tips & Tricks", "devops-tips-tricks"),
        ("  Café  Science ", "cafe-science"),
        ("C++ / Rust", "c-rust"),
        ("x" * 60, "x" * 36),
    ],
)
def test_link_part_is_made_from_the_name(name: str, slug: str) -> None:
    """Link part is made from the name."""
    assert slug_from(name) == slug


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 61},
        {"name": "Dev​Ops"},
        {"name": "Dev‮Ops"},
        {"name": "DevOps", "slug": "admin"},
        {"name": "DevOps", "created_by": str(uuid.uuid4())},
        {"name": "DevOps", "description": "x" * 201},
    ],
)
def test_bad_input_is_422(body: dict[str, object]) -> None:
    """Bad input is 422."""
    response = TestClient(create_app()).post("/groups", json=body, headers=_auth(uuid.uuid4()))
    assert response.status_code == 422


@beta
def test_create_numbered_duplicates_reserved_and_rate_limit(
    beta_user: tuple[uuid.UUID, str],
) -> None:
    """Create numbered duplicates reserved and rate limit."""
    user_id, handle = beta_user
    headers = _auth(user_id, handle)
    name = f"zz test {uuid.uuid4().hex[:8]}"
    with TestClient(create_app()) as client:
        try:
            created = client.post("/groups", json={"name": f" {name} "}, headers=headers)
            assert created.status_code == 201
            assert "created_by" not in created.json()
            assert {"id", "slug", "name", "description"} <= set(created.json())
            assert created.json()["name"] == name
            assert created.json()["slug"] == slug_from(name)

            listed = client.get("/groups").json()
            assert slug_from(name) in [g["slug"] for g in listed]

            again = client.post("/groups", json={"name": name}, headers=headers)
            assert again.status_code == 201 and again.json()["slug"] == f"{slug_from(name)}-2"

            reserved = client.post("/groups", json={"name": "Admin"}, headers=headers)
            assert reserved.status_code == 422
            short = client.post("/groups", json={"name": "!"}, headers=headers)
            assert short.status_code == 422

            more = client.post("/groups", json={"name": f"{name} b"}, headers=headers)
            assert more.status_code == 201
            limited = client.post("/groups", json={"name": f"{name} c"}, headers=headers)
            assert limited.status_code == 429 and CREATE_LIMIT == 5
            assert int(limited.headers["Retry-After"]) > 0
        finally:
            client.portal.call(client.app.state.redis.delete, f"ratelimit:groups:create:{user_id}")
