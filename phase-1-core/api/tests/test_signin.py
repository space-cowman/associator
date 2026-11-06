"""Sign in with GitHub / Google: the OAuth flow (providers faked), sessions, rotation, logout."""

import base64
import hashlib
import json
import time
import uuid
from collections.abc import Iterator
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from tests.conftest import beta, run_sql

from api.config import get_settings
from api.main import create_app
from api.routes.signin import (
    REFRESH_COOKIE,
    SIGNUP_COOKIE,
    STATE_COOKIE,
    TERMS_VERSION,
    account_hash,
    pkce_pair,
)

PEPPER = "pepper-" + "p" * 40  # pragma: allowlist secret
CSRF = {"X-Requested-With": "platform"}
TERMS = {"accept_terms": True, "terms_version": TERMS_VERSION}


@pytest.fixture(autouse=True)
def oauth_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Use test sign-in settings."""
    monkeypatch.setenv("IDENTITY_PEPPER", PEPPER)
    monkeypatch.setenv("GITHUB_CLIENT_ID", "gh-client")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "gh-secret")  # pragma: allowlist secret
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "g-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "g-secret")  # pragma: allowlist secret
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def cookies_from(response: httpx.Response) -> dict[str, str]:
    """Read the cookies a response set."""
    jar: dict[str, str] = {}
    for header in response.headers.get_list("set-cookie"):
        parsed = SimpleCookie()
        parsed.load(header)
        for name, morsel in parsed.items():
            jar[name] = morsel.value
    return jar


def cookie_header(**cookies: str) -> dict[str, str]:
    """A Cookie header from saved cookies."""
    return {"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())}


def test_pkce_challenge_is_s256_of_verifier() -> None:
    """Pkce challenge is s256 of verifier."""
    verifier, challenge = pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert challenge == expected.decode() and len(verifier) >= 43


def test_account_hash_is_keyed_and_per_provider() -> None:
    """Account hash is keyed and per provider."""
    a = account_hash("github", "42")
    assert a != account_hash("google", "42")
    assert a != hashlib.sha256(b"github:42").hexdigest()
    assert len(a) == 64


def test_providers_lists_configured_buttons(monkeypatch: pytest.MonkeyPatch) -> None:
    """Providers lists configured buttons."""
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET")
    get_settings.cache_clear()
    assert TestClient(create_app()).get("/auth/providers").json() == {
        "github": True,
        "google": False,
    }


def test_unconfigured_provider_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unconfigured provider is 503."""
    monkeypatch.delenv("GITHUB_CLIENT_ID")
    get_settings.cache_clear()
    response = TestClient(create_app()).get("/auth/github/start", follow_redirects=False)
    assert response.status_code == 503


@pytest.mark.parametrize("path", ["/auth/refresh", "/auth/logout"])
def test_cookie_endpoints_need_the_csrf_header(path: str) -> None:
    """Cookie endpoints need the csrf header."""
    client = TestClient(create_app(), base_url="https://testserver")
    assert client.post(path, headers=cookie_header(**{REFRESH_COOKIE: "x"})).status_code == 403
    other_site = {**CSRF, "Origin": "https://evil.example"}
    assert client.post(path, headers=other_site).status_code == 403


def test_callback_without_matching_state_cookie_is_refused() -> None:
    """Callback without matching state cookie is refused."""
    client = TestClient(create_app(), base_url="https://testserver")
    response = client.get(
        "/auth/github/callback?code=c&state=s1",
        headers=cookie_header(**{STATE_COOKIE: "s2"}),
        follow_redirects=False,
    )
    assert response.status_code == 303 and response.headers["location"] == "/signin?error=expired"


def test_provider_error_goes_back_to_sign_in() -> None:
    """Provider error goes back to sign in."""
    response = TestClient(create_app()).get(
        "/auth/google/callback?error=access_denied", follow_redirects=False
    )
    assert response.headers["location"] == "/signin?error=cancelled"


@pytest.mark.parametrize("handle", ["ab", "Has-Caps", "x" * 31, "spa ce", "dot.ted"])
def test_bad_handles_are_422(handle: str) -> None:
    """Bad handles are 422."""
    response = TestClient(create_app(), base_url="https://testserver").post(
        "/auth/signup", json={"handle": handle, **TERMS}, headers=CSRF
    )
    assert response.status_code == 422


def fake_providers(account: str) -> httpx.AsyncClient:
    """GitHub and Google, faked: they check what we send and answer like the real ones."""

    def handle(request: httpx.Request) -> httpx.Response:
        """Answer like GitHub and Google."""
        url = str(request.url)
        if url == "https://github.com/login/oauth/access_token":
            form = parse_qs(request.content.decode())
            assert form["client_secret"] == ["gh-secret"] and form["code_verifier"]
            return httpx.Response(200, json={"access_token": "gho_fake"})
        if url == "https://api.github.com/user":
            assert request.headers["Authorization"] == "Bearer gho_fake"
            return httpx.Response(200, json={"id": int(account), "login": "someone"})
        if url.startswith("https://api.github.com/applications/"):
            return httpx.Response(204)
        if url == "https://oauth2.googleapis.com/token":
            form = parse_qs(request.content.decode())
            assert form["grant_type"] == ["authorization_code"] and form["code_verifier"]
            claims = {
                "iss": "https://accounts.google.com",
                "aud": "g-client",
                "sub": account,
                "exp": int(time.time()) + 300,
            }
            return httpx.Response(200, json={"id_token": jwt.encode(claims, "x" * 32)})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


def sign_in(client: TestClient, provider: str) -> httpx.Response:
    """Sign in through a fake provider."""
    start = client.get(f"/auth/{provider}/start", follow_redirects=False)
    assert start.status_code == 302
    query = parse_qs(urlparse(start.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == [f"https://associator.space/api/auth/{provider}/callback"]
    state = query["state"][0]
    assert cookies_from(start)[STATE_COOKIE] == state
    assert "httponly" in start.headers["set-cookie"].lower()
    return client.get(
        f"/auth/{provider}/callback?code=abc&state={state}",
        headers=cookie_header(**{STATE_COOKIE: state}),
        follow_redirects=False,
    )


@beta
@pytest.mark.parametrize("provider", ["github", "google"])
def test_full_flow_new_account_rotation_reuse_and_logout(provider: str) -> None:
    """Full flow new account rotation reuse and logout."""
    handle = f"zz-signin-{uuid.uuid4().hex[:8]}"
    account = str(900_000_000 + int(uuid.uuid4().int % 1_000_000))
    with TestClient(create_app(), base_url="https://testserver") as client:
        client.app.state.oauth_http = fake_providers(account)  # type: ignore[attr-defined]
        try:
            first = sign_in(client, provider)
            assert first.headers["location"] == "/signin/handle"
            ticket = cookies_from(first)[SIGNUP_COOKIE]

            signup = {"headers": {**CSRF, **cookie_header(**{SIGNUP_COOKIE: ticket})}}
            reserved = client.post("/auth/signup", json={"handle": "admin", **TERMS}, **signup)
            assert reserved.status_code == 422
            created = client.post("/auth/signup", json={"handle": handle, **TERMS}, **signup)
            assert created.status_code == 200 and created.json()["handle"] == handle
            session = cookies_from(created)[REFRESH_COOKIE]
            set_cookie = ";".join(created.headers.get_list("set-cookie")).lower()
            assert "samesite=strict" in set_cookie and "secure" in set_cookie
            me = client.get(
                "/me", headers={"Authorization": f"Bearer {created.json()['access_token']}"}
            )
            assert me.json()["handle"] == handle

            again = sign_in(client, provider)
            assert again.headers["location"] == "/signin/done"

            refreshed = client.post(
                "/auth/refresh", headers={**CSRF, **cookie_header(**{REFRESH_COOKIE: session})}
            )
            assert refreshed.status_code == 200
            new_session = cookies_from(refreshed)[REFRESH_COOKIE]
            assert new_session != session

            run_sql(
                "UPDATE sessions SET used_at = now() - interval '1 minute' WHERE token_hash = :h",
                {"h": hashlib.sha256(session.encode()).hexdigest()},
                as_owner=True,
            )
            stolen = client.post(
                "/auth/refresh", headers={**CSRF, **cookie_header(**{REFRESH_COOKIE: session})}
            )
            assert stolen.status_code == 401
            victim = client.post(
                "/auth/refresh", headers={**CSRF, **cookie_header(**{REFRESH_COOKIE: new_session})}
            )
            assert victim.status_code == 401

            fresh = cookies_from(sign_in(client, provider))[REFRESH_COOKIE]
            out = client.post(
                "/auth/logout", headers={**CSRF, **cookie_header(**{REFRESH_COOKIE: fresh})}
            )
            assert out.status_code == 204
            after = client.post(
                "/auth/refresh", headers={**CSRF, **cookie_header(**{REFRESH_COOKIE: fresh})}
            )
            assert after.status_code == 401
        finally:
            run_sql("DELETE FROM users WHERE handle = :h", {"h": handle}, as_owner=True)
            client.portal.call(client.app.state.redis.delete, "ratelimit:signin:testclient")  # type: ignore[attr-defined]
            client.portal.call(client.app.state.redis.delete, "ratelimit:signup:testclient")  # type: ignore[attr-defined]


@beta
def test_state_is_single_use() -> None:
    """State is single use."""
    with TestClient(create_app(), base_url="https://testserver") as client:
        client.app.state.oauth_http = fake_providers("123")  # type: ignore[attr-defined]
        start = client.get("/auth/github/start", follow_redirects=False)
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        stored = client.portal.call(client.app.state.redis.get, f"oauth:state:{state}")  # type: ignore[attr-defined]
        assert json.loads(stored)["provider"] == "github"
        url = f"/auth/google/callback?code=abc&state={state}"
        with_cookie = cookie_header(**{STATE_COOKIE: state})
        wrong = client.get(url, headers=with_cookie, follow_redirects=False)
        assert wrong.headers["location"] == "/signin?error=expired"
        url = f"/auth/github/callback?code=abc&state={state}"
        replay = client.get(url, headers=with_cookie, follow_redirects=False)
        assert replay.headers["location"] == "/signin?error=expired"
        client.portal.call(client.app.state.redis.delete, "ratelimit:signin:testclient")  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "body",
    [
        {"handle": "someone"},
        {"handle": "someone", "accept_terms": False, "terms_version": TERMS_VERSION},
        {"handle": "someone", "accept_terms": "yes", "terms_version": TERMS_VERSION},
    ],
)
def test_signup_needs_explicit_consent(body: dict[str, object]) -> None:
    """Signup needs explicit consent."""
    response = TestClient(create_app(), base_url="https://testserver").post(
        "/auth/signup", json=body, headers=CSRF
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("handle", "reserved"),
    [
        ("platform-ai", True),
        ("claude", True),
        ("gpt-4o", True),
        ("gemini2", True),
        ("grok-fan", True),
        ("deepseek", True),
        ("admin", True),
        ("claudette", False),
        ("ravi", False),
        ("groovy-dev", False),
    ],
)
def test_ai_like_handles_are_reserved(handle: str, reserved: bool) -> None:
    """Ai like handles are reserved."""
    from api.routes.signin import reserved_handle

    assert reserved_handle(handle) is reserved
