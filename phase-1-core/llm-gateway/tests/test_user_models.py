import base64
import json
import uuid
from collections.abc import Iterator

import httpx2
import pytest
from fastapi.testclient import TestClient
from tests.fake_kms import FakeKms

from gateway import main, providers, telemetry
from gateway.config import get_settings

KEY = "sk-or-v1-" + "f00d" * 16  # pragma: allowlist secret
USER, MODEL_ID = uuid.uuid4(), uuid.uuid4()
CTX = {"purpose": "user-model-key", "user_id": str(USER), "model_id": str(MODEL_ID)}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A test gateway with fake KMS."""
    monkeypatch.setenv("USER_KEYS_KMS_ARN", "arn:aws:kms:ap-south-1:000000000000:key/test")
    get_settings.cache_clear()
    with TestClient(main.create_app()) as c:
        c.app.state.kms = FakeKms()  # type: ignore[attr-defined]
        yield c
    get_settings.cache_clear()


def ciphertext(client: TestClient, ctx: dict[str, str] = CTX) -> str:
    """A test key encrypted for a person and model."""
    blob = client.app.state.kms.encrypt("k", KEY.encode(), ctx)["CiphertextBlob"]  # type: ignore[attr-defined]
    return base64.b64encode(blob).decode()


def body(ct: str, user: uuid.UUID = USER, model_id: uuid.UUID = MODEL_ID) -> dict[str, object]:
    """A request with a person's own model."""
    return {
        "request_id": "req-12345678",
        "user_id": str(user),
        "model": "user",
        "messages": [{"role": "user", "content": "hello"}],
        "user_model": {
            "model_id": str(model_id),
            "provider": "openrouter",
            "model": "google/gemma-4-31b-it:free",
            "key_ciphertext": ct,
        },
    }


@pytest.fixture
def openrouter(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Answers OpenRouter calls locally; records the key it was called with."""
    seen: dict[str, object] = {"answered_by": "google/gemma-4-31b-it"}
    real = providers.OpenAICompatible.__init__

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Answer like OpenRouter."""
        seen["auth"] = request.headers["authorization"]
        seen["model"] = json.loads(request.content)["model"]
        return httpx2.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "created": 0,
                "model": seen["answered_by"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "Hi from Gemma"},
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9},
            },
            headers={"x-ratelimit-remaining-requests": "7"},
        )

    def patched(self: object, *args: object, **kwargs: object) -> None:
        """Use the fake OpenRouter."""
        kwargs["http_client"] = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        real(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(providers.OpenAICompatible, "__init__", patched)
    return seen


def test_user_key_is_decrypted_for_the_call(
    client: TestClient, openrouter: dict[str, object]
) -> None:
    """User key is decrypted for the call."""
    r = client.post("/complete", json=body(ciphertext(client)))
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "Hi from Gemma" and r.json()["provider"] == "openrouter"
    assert openrouter["auth"] == f"Bearer {KEY}"
    assert openrouter["model"] == "google/gemma-4-31b-it:free"
    assert KEY not in r.text
    assert not any(k[0] == "openrouter" for k in telemetry._quota)


@pytest.mark.parametrize("who", ["other user", "other model", "tampered"])
def test_key_bound_to_its_owner_and_model(
    client: TestClient, openrouter: dict[str, object], who: str
) -> None:
    """Key bound to its owner and model."""
    ct = ciphertext(client)
    if who == "other user":
        request = body(ct, user=uuid.uuid4())
    elif who == "other model":
        request = body(ct, model_id=uuid.uuid4())
    else:
        request = body(base64.b64encode(b"x" * 48).decode())
    r = client.post("/complete", json=request)
    assert r.status_code == 403 and r.json() == {"detail": "key_unavailable"}
    assert "auth" not in openrouter


def test_a_different_answering_model_is_rejected(
    client: TestClient, openrouter: dict[str, object]
) -> None:
    """A different answering model is rejected."""
    openrouter["answered_by"] = "some/other-paid-model"
    r = client.post("/complete", json=body(ciphertext(client)))
    assert r.status_code == 502 and r.json() == {"detail": "model_mismatch"}


@pytest.mark.parametrize(
    "change",
    [{"model": "user", "user_model": None}, {"model": "fake"}],
)
def test_user_model_only_with_model_user(client: TestClient, change: dict[str, object]) -> None:
    """User model only with model user."""
    request = {**body(ciphertext(client)), **change}
    assert client.post("/complete", json=request).status_code == 422


def test_same_model_rule() -> None:
    """Same model rule."""
    assert providers.same_model("google/gemma-4-31b-it:free", "google/gemma-4-31b-it")
    assert providers.same_model("openai/gpt-4o", "openai/gpt-4o-2026-05-13")
    assert not providers.same_model("google/gemma-4-31b-it:free", "google/gemma-4-12b-it")


@pytest.fixture
def embeddings(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Answers embedding calls locally (vectors out of order, as providers may send them)."""
    seen: dict[str, object] = {"status": 200}
    real = providers.OpenAICompatible.__init__

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Answer embedding requests."""
        sent = json.loads(request.content)
        seen.update(
            auth=request.headers["authorization"], model=sent["model"], path=request.url.path
        )
        if seen["status"] != 200:
            return httpx2.Response(int(seen["status"]), json={"error": {"message": "bad key"}})  # type: ignore[call-overload]
        data = [
            {"object": "embedding", "index": i, "embedding": [float(i), 0.5]}
            for i in range(len(sent["input"]))
        ]
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "model": sent["model"],
                "data": data[::-1],
                "usage": {"prompt_tokens": 7, "total_tokens": 7},
            },
        )

    def patched(self: object, *args: object, **kwargs: object) -> None:
        """Use the fake embeddings."""
        kwargs["http_client"] = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        real(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(providers.OpenAICompatible, "__init__", patched)
    return seen


def embed_body(ct: str, provider: str = "openai") -> dict[str, object]:
    """A request for embeddings."""
    return {
        "request_id": "req-12345678",
        "user_id": str(USER),
        "user_model": {
            "model_id": str(MODEL_ID),
            "provider": provider,
            "model": "gpt-5-mini",
            "key_ciphertext": ct,
        },
        "texts": ["I live in Pune", "I use a Mac with arm64"],
    }


def test_embed_uses_the_persons_key_and_keeps_order(
    client: TestClient, embeddings: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    """Embed uses the persons key and keeps order."""
    r = client.post("/embed", json=embed_body(ciphertext(client)))
    assert r.status_code == 200, r.text
    assert r.json() == {"model": "text-embedding-3-small", "vectors": [[0.0, 0.5], [1.0, 0.5]]}
    assert embeddings["auth"] == f"Bearer {KEY}" and str(embeddings["path"]).endswith("/embeddings")
    logged = capsys.readouterr()
    assert "Pune" not in logged.out + logged.err and KEY not in logged.out + logged.err


def test_embed_providers_and_errors(client: TestClient, embeddings: dict[str, object]) -> None:
    """Embed providers and errors."""
    ct = ciphertext(client)
    r = client.post("/embed", json=embed_body(ct, "gemini"))
    assert r.status_code == 200 and embeddings["model"] == "gemini-embedding-001"
    none = client.post("/embed", json=embed_body(ct, "anthropic"))
    assert none.status_code == 409 and none.json()["detail"] == "no_embeddings"
    embeddings["status"] = 401
    bad = client.post("/embed", json=embed_body(ct))
    assert bad.status_code == 502 and bad.json()["detail"]["reason"] == "invalid_key"
    assert "bad key" not in bad.text
    too_many = {**embed_body(ct), "texts": ["x"] * 101}
    assert client.post("/embed", json=too_many).status_code == 422
