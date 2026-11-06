import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from tests.conftest import auth_header, beta, run_sql
from tests.fake_kms import FakeKms

from api.auth import issue_token
from api.config import get_settings
from api.main import create_app

KEY = "sk-or-v1-" + "a1b2c3d4" * 8  # pragma: allowlist secret
GOOD = {"provider": "openrouter", "model": "google/gemma-4-31b-it:free", "api_key": KEY}


@pytest.fixture
def kms_arn(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Use a test KMS key."""
    monkeypatch.setenv("USER_KEYS_KMS_ARN", "arn:aws:kms:ap-south-1:000000000000:key/test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_needs_sign_in() -> None:
    """Needs sign in."""
    assert TestClient(create_app()).post("/me/models", json=GOOD).status_code == 401


def test_agent_cannot_manage_keys() -> None:
    """Agent cannot manage keys."""
    agent = {"Authorization": f"Bearer {issue_token(uuid.uuid4(), 'bot', 'agent')}"}
    assert TestClient(create_app()).post("/me/models", json=GOOD, headers=agent).status_code == 403


@pytest.mark.parametrize(
    "override",
    [
        {"provider": "groq"},
        {"model": "openai/gpt-5"},
        {"model": "bad model name"},
        {"api_key": "short"},  # pragma: allowlist secret
        {"api_key": KEY + " extra"},
        {"api_key": KEY + "‮"},
        {"owner": "someone-else"},
    ],
)
def test_bad_input_is_422_and_never_echoes_the_key(override: dict[str, object]) -> None:
    """Bad input is 422 and never echoes the key."""
    response = TestClient(create_app()).post(
        "/me/models", json={**GOOD, **override}, headers=auth_header(uuid.uuid4())
    )
    assert response.status_code == 422
    assert KEY not in response.text and "a1b2c3d4" not in response.text


def test_without_kms_configured_is_503() -> None:
    """Without kms configured is 503."""
    response = TestClient(create_app()).post(
        "/me/models", json=GOOD, headers=auth_header(uuid.uuid4())
    )
    assert response.status_code == 503


@beta
def test_save_up_to_three_patch_delete(beta_user: tuple[uuid.UUID, str], kms_arn: None) -> None:
    """Save up to three patch delete."""
    user_id, handle = beta_user
    me = auth_header(user_id, handle)
    other = uuid.uuid4()
    run_sql(
        "INSERT INTO users (id, handle, auth_provider, provider_user_id_hash)"
        " VALUES (:id, :h, 'dev', :p)",
        {"id": other, "h": f"zz-test-{other.hex[:8]}", "p": other.hex},
    )
    fake = FakeKms()
    second = {**GOOD, "model": "qwen/qwen3-coder:free", "label": "Coder", "strengths": ["coding"]}
    third = {**GOOD, "model": "meta-llama/llama-4-scout:free"}
    with TestClient(create_app()) as client:
        client.app.state.kms = fake  # type: ignore[attr-defined]
        try:
            saved = client.post("/me/models", json=GOOD, headers=me)
            assert saved.status_code == 201, saved.text
            out = saved.json()
            assert out["key_last4"] == KEY[-4:] and set(out) == {
                "id",
                "provider",
                "model",
                "label",
                "strengths",
                "enabled",
                "key_last4",
                "created_at",
            }
            assert out["enabled"] is True and out["strengths"] == [] and out["label"] is None
            assert KEY not in saved.text

            assert client.post("/me/models", json=GOOD, headers=me).status_code == 409
            assert len(fake._store) == 1

            coder = client.post("/me/models", json=second, headers=me).json()
            assert coder["label"] == "Coder" and coder["strengths"] == ["coding"]
            assert client.post("/me/models", json=third, headers=me).status_code == 201
            fourth = {**GOOD, "model": "openai/gpt-oss-20b:free"}
            full = client.post("/me/models", json=fourth, headers=me)
            assert full.status_code == 409 and "up to 3" in full.text
            assert len(fake._store) == 3

            listed = client.get("/me/models", headers=me).json()
            assert [m["id"] for m in listed][:2] == [out["id"], coder["id"]]
            assert client.get("/me/models", headers=auth_header(other)).json() == []

            blob, (plain, ctx) = next(iter(fake._store.items()))
            assert plain == KEY.encode() and blob != plain
            assert ctx == {
                "purpose": "user-model-key",
                "user_id": str(user_id),
                "model_id": out["id"],
            }
            with pytest.raises(Exception, match="InvalidCiphertext"):
                fake.decrypt(blob, "k", {**ctx, "user_id": str(other)})

            url = f"/me/models/{out['id']}"
            patch = {"enabled": False, "label": "Main", "strengths": ["reasoning", "writing"]}
            changed = client.patch(url, json=patch, headers=me)
            assert changed.status_code == 200, changed.text
            assert {k: changed.json()[k] for k in patch} == patch
            for bad in (
                {},
                {"strengths": ["fast"]},
                {"strengths": ["cheap", "cheap"]},
                {"api_key": KEY},
                {"label": "x" * 41},
            ):
                r = client.patch(url, json=bad, headers=me)
                assert r.status_code == 422 and KEY not in r.text, bad
            assert client.patch(url, json=patch, headers=auth_header(other)).status_code == 404
            agent = {"Authorization": f"Bearer {issue_token(user_id, handle, 'agent')}"}
            assert client.patch(url, json=patch, headers=agent).status_code == 403

            assert client.delete(url, headers=auth_header(other)).status_code == 404
            assert client.delete(url, headers=me).status_code == 204
            assert client.post("/me/models", json=GOOD, headers=me).status_code == 201
        finally:
            client.portal.call(client.app.state.redis.delete, f"ratelimit:models:save:{user_id}")
            run_sql("DELETE FROM model_registry WHERE user_id = :u", {"u": user_id}, as_owner=True)
            run_sql("DELETE FROM users WHERE id = :u", {"u": other}, as_owner=True)
