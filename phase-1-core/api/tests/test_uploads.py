import io
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from tests.conftest import auth_header, beta, run_sql, use_real_safety
from tests.fake_s3 import FakeS3

from api.auth import issue_token
from api.config import get_settings
from api.main import create_app


def png() -> bytes:
    """A small test image."""
    out = io.BytesIO()
    Image.new("RGB", (8, 8), "teal").save(out, format="PNG")
    return out.getvalue()


@pytest.fixture
def bucket(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Use a fake bucket."""
    monkeypatch.setenv("ATTACHMENTS_BUCKET", "test-bucket")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_upload_needs_a_human_and_an_allowed_type(bucket: None) -> None:
    """Upload needs a human and an allowed type."""
    client = TestClient(create_app())
    body = {"filename": "a.png", "content_type": "image/png", "size_bytes": 10}
    assert client.post("/uploads", json=body).status_code == 401
    agent = {"Authorization": f"Bearer {issue_token(uuid.uuid4(), 'bot', 'agent')}"}
    assert client.post("/uploads", json=body, headers=agent).status_code == 403
    me = auth_header(uuid.uuid4())
    for bad in (
        {**body, "content_type": "image/svg+xml"},
        {**body, "content_type": "text/html"},
        {**body, "size_bytes": 0},
        {**body, "extra": 1},
    ):
        assert client.post("/uploads", json=bad, headers=me).status_code == 422


@beta
def test_upload_check_attach_and_serve(bucket: None, beta_user: tuple[uuid.UUID, str]) -> None:
    """Upload check attach and serve."""
    user_id, handle = beta_user
    me = auth_header(user_id, handle)
    group = f"zz-test-{uuid.uuid4().hex[:8]}"
    run_sql(
        "INSERT INTO topic_groups (slug, name, created_by) VALUES (:s, 'T', :u)",
        {"s": group, "u": user_id},
    )
    s3 = FakeS3()
    with TestClient(create_app()) as client:
        client.app.state.s3 = s3  # type: ignore[attr-defined]
        use_real_safety(client.app)  # type: ignore[arg-type]
        try:
            image = png()
            huge = {"filename": "x.png", "content_type": "image/png", "size_bytes": 6 * 1024 * 1024}
            assert client.post("/uploads", json=huge, headers=me).status_code == 422

            start = client.post(
                "/uploads",
                json={
                    "filename": "../../my shot.png",
                    "content_type": "image/png",
                    "size_bytes": len(image),
                },
                headers=me,
            )
            assert start.status_code == 201
            up = start.json()
            assert ["content-length-range", 1, len(image)] in s3.forms[-1]["conditions"]
            assert client.post(f"/uploads/{up['id']}/complete", headers=me).status_code == 409
            s3.objects[f"pending/{up['id']}"] = image
            assert (
                client.post(
                    f"/uploads/{up['id']}/complete", headers=auth_header(uuid.uuid4())
                ).status_code
                == 404
            )
            done = client.post(f"/uploads/{up['id']}/complete", headers=me)
            assert done.status_code == 200 and done.json()["filename"] == "my shot.png"
            assert f"pending/{up['id']}" not in s3.objects and f"files/{up['id']}" in s3.objects

            assert client.get(f"/attachments/{up['id']}", follow_redirects=False).status_code == 404

            posted = client.post(
                "/threads",
                json={"group": group, "text": "see the screenshot", "attachments": [up["id"]]},
                headers=me,
            )
            assert posted.status_code == 201, posted.text
            assert posted.json()["attachments"][0]["kind"] == "image"
            served = client.get(f"/attachments/{up['id']}", follow_redirects=False)
            assert served.status_code == 307 and "signed" in served.headers["location"]

            again = client.post(
                "/threads",
                json={"group": group, "text": "again", "attachments": [up["id"]]},
                headers=me,
            )
            assert again.status_code == 422

            bad = client.post(
                "/uploads",
                json={"filename": "x.png", "content_type": "image/png", "size_bytes": 20},
                headers=me,
            ).json()
            s3.objects[f"pending/{bad['id']}"] = b"#!/bin/sh\nrm -rf /\n"
            rejected = client.post(f"/uploads/{bad['id']}/complete", headers=me)
            assert rejected.status_code == 422 and f"pending/{bad['id']}" not in s3.objects

            secret = b"config\nexport DB_PASSWORD=s3cr3tPass99\n"  # pragma: allowlist secret
            t = client.post(
                "/uploads",
                json={
                    "filename": "app.log",
                    "content_type": "text/plain",
                    "size_bytes": len(secret),
                },
                headers=me,
            ).json()
            s3.objects[f"pending/{t['id']}"] = secret
            leaked = client.post(f"/uploads/{t['id']}/complete", headers=me)
            assert leaked.status_code == 422 and "s3cr3t" not in leaked.text
        finally:
            client.portal.call(client.app.state.redis.delete, f"ratelimit:uploads:{user_id}")
            client.portal.call(client.app.state.redis.delete, f"ratelimit:threads:create:{user_id}")
