"""Sign in with GitHub or Google (OAuth 2.0 authorization code + PKCE), and browser sessions."""

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from api import ratelimit
from api.auth import issue_token
from api.config import get_settings

log = logging.getLogger("api.signin")
router = APIRouter(prefix="/auth")

Provider = Literal["github", "google"]

STATE_COOKIE = "__Secure-pp_oauth"
SIGNUP_COOKIE = "__Secure-pp_signup"
REFRESH_COOKIE = "__Secure-pp_refresh"
COOKIE_PATH = "/api/auth/"
FLOW_SECONDS = 600
SIGNUP_SECONDS = 900
SESSION_DAYS = 30
REUSE_GRACE = timedelta(seconds=15)
CSRF_HEADER = "platform"

RESERVED_HANDLES = frozenset(
    {
        "admin", "administrator", "api", "auth", "help", "mod", "moderator", "null", "owner",
        "platform", "project-platform", "root", "security", "signin", "staff", "support",
        "system", "undefined", "you",
        "associator", "platform-ai", "ai", "bot", "agent", "assistant",
    }
)  # fmt: skip
AI_NAMES = re.compile(
    r"^(gpt|chatgpt|openai|claude|anthropic|gemini|bard|llama|meta-ai|grok|xai|deepseek|mistral"
    r"|mixtral|qwen|copilot|perplexity|cohere|groq|openrouter|nemotron)(-|\d|$)"
)


def reserved_handle(handle: str) -> bool:
    """Whether a handle is reserved for AI names."""
    return handle in RESERVED_HANDLES or AI_NAMES.match(handle) is not None


AUTHORIZE = {
    "github": "https://github.com/login/oauth/authorize",
    "google": "https://accounts.google.com/o/oauth2/v2/auth",
}
TOKEN = {
    "github": "https://github.com/login/oauth/access_token",
    "google": "https://oauth2.googleapis.com/token",
}
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


def _client(provider: Provider) -> tuple[str, str]:
    """The OAuth settings of a sign-in provider."""
    s = get_settings()
    cid, secret = (
        (s.github_client_id, s.github_client_secret)
        if provider == "github"
        else (s.google_client_id, s.google_client_secret)
    )
    if not cid or secret is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "This sign-in is not available")
    return cid, secret.get_secret_value()


def _redirect_uri(provider: Provider) -> str:
    """Where the provider sends people back to."""
    return f"{get_settings().public_url}/api/auth/{provider}/callback"


def pkce_pair() -> tuple[str, str]:
    """PKCE (RFC 7636, S256): the verifier stays here, only its hash goes to the provider."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def account_hash(provider: Provider, account_id: str) -> str:
    """HMAC of the provider's account id with a server-side key (not reversible from the DB)."""
    pepper = get_settings().identity_pepper
    if pepper is None:
        raise RuntimeError("IDENTITY_PEPPER is not set")
    msg = f"{provider}:{account_id}".encode()
    return hmac.new(pepper.get_secret_value().encode(), msg, hashlib.sha256).hexdigest()


def _token_hash(token: str) -> str:
    """A one-way hash of a session token."""
    return hashlib.sha256(token.encode()).hexdigest()


def _set_cookie(response: Response, name: str, value: str, max_age: int, same_site: str) -> None:
    """Set a secure cookie."""
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path=COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite=same_site,  # type: ignore[arg-type]
    )


def _clear_cookie(response: Response, name: str) -> None:
    """Remove a cookie."""
    response.delete_cookie(name, path=COOKIE_PATH, secure=True, httponly=True)


def _fail(reason: str) -> RedirectResponse:
    """Back to the sign-in page with a fixed reason code (never provider text)."""
    response = RedirectResponse(f"/signin?error={reason}", status.HTTP_303_SEE_OTHER)
    _clear_cookie(response, STATE_COOKIE)
    return response


def _check_csrf(request: Request, x_requested_with: str | None) -> None:
    """Refuse cookie requests without the CSRF header."""
    origin = request.headers.get("origin")
    if x_requested_with != CSRF_HEADER or (origin and origin != get_settings().public_url):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")


def _client_ip(request: Request) -> str:
    """The visitor's IP address."""
    return request.client.host if request.client else "unknown"


async def _github_account(http: httpx.AsyncClient, code: str, verifier: str) -> str:
    """Get the GitHub account id after sign-in."""
    cid, secret = _client("github")
    token = await http.post(
        TOKEN["github"],
        headers={"Accept": "application/json"},
        data={
            "client_id": cid,
            "client_secret": secret,
            "code": code,
            "redirect_uri": _redirect_uri("github"),
            "code_verifier": verifier,
        },
    )
    access = token.json().get("access_token") if token.status_code == 200 else None
    if not isinstance(access, str):
        raise ValueError("no access token")
    user = await http.get(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {access}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    account = user.json().get("id") if user.status_code == 200 else None
    try:
        await http.request(
            "DELETE",
            f"https://api.github.com/applications/{cid}/token",
            auth=(cid, secret),
            json={"access_token": access},
        )
    except httpx.HTTPError:
        pass
    if not isinstance(account, int):
        raise ValueError("no account id")
    return str(account)


async def _google_account(http: httpx.AsyncClient, code: str, verifier: str) -> str:
    """Get the Google account id after sign-in."""
    cid, secret = _client("google")
    token = await http.post(
        TOKEN["google"],
        data={
            "client_id": cid,
            "client_secret": secret,
            "code": code,
            "redirect_uri": _redirect_uri("google"),
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        },
    )
    id_token = token.json().get("id_token") if token.status_code == 200 else None
    if not isinstance(id_token, str):
        raise ValueError("no id token")
    claims = jwt.decode(id_token, options={"verify_signature": False})
    now = datetime.now(UTC).timestamp()
    if (
        claims.get("iss") not in GOOGLE_ISSUERS
        or claims.get("aud") != cid
        or not isinstance(claims.get("exp"), int | float)
        or claims["exp"] < now
        or not isinstance(claims.get("sub"), str)
        or not claims["sub"]
    ):
        raise ValueError("bad id token")
    return str(claims["sub"])


async def _new_session(
    conn: AsyncConnection, user_id: uuid.UUID, family: uuid.UUID | None = None
) -> str:
    """Start a new sign-in session."""
    token = secrets.token_urlsafe(32)
    await conn.execute(
        text(
            "INSERT INTO sessions (user_id, family, token_hash, expires_at)"
            " VALUES (:u, :f, :h, now() + make_interval(days => :d))"
        ),
        {"u": user_id, "f": family or uuid.uuid4(), "h": _token_hash(token), "d": SESSION_DAYS},
    )
    return token


def _session_cookie(response: Response, token: str) -> None:
    """Set the session cookie."""
    _set_cookie(response, REFRESH_COOKIE, token, SESSION_DAYS * 86400, "strict")


@router.get("/{provider}/start")
async def start(provider: Provider, request: Request) -> RedirectResponse:
    """Send the person to the provider to sign in."""
    cid, _ = _client(provider)
    await ratelimit.enforce(request, f"ratelimit:signin:{_client_ip(request)}", 20, 600)
    state = secrets.token_urlsafe(32)
    verifier, challenge = pkce_pair()
    await request.app.state.redis.set(
        f"oauth:state:{state}",
        json.dumps({"provider": provider, "verifier": verifier}),
        ex=FLOW_SECONDS,
    )
    params = {
        "client_id": cid,
        "redirect_uri": _redirect_uri(provider),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if provider == "google":
        params |= {"response_type": "code", "scope": "openid", "prompt": "select_account"}
    response = RedirectResponse(f"{AUTHORIZE[provider]}?{urlencode(params)}", status.HTTP_302_FOUND)
    _set_cookie(response, STATE_COOKIE, state, FLOW_SECONDS, "lax")
    return response


@router.get("/{provider}/callback")
async def callback(
    provider: Provider,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    state_cookie: Annotated[str | None, Cookie(alias=STATE_COOKIE)] = None,
) -> RedirectResponse:
    """Finish sign-in when the provider sends the person back."""
    if error or not code or not state:
        return _fail("cancelled")
    if not state_cookie or not hmac.compare_digest(state, state_cookie):
        return _fail("expired")
    raw = await request.app.state.redis.getdel(f"oauth:state:{state}")
    flow = json.loads(raw) if raw else None
    if not flow or flow.get("provider") != provider:
        return _fail("expired")
    try:
        http = request.app.state.oauth_http
        fetch = _github_account if provider == "github" else _google_account
        account = await fetch(http, code, flow["verifier"])
    except (httpx.HTTPError, ValueError, jwt.PyJWTError) as exc:
        log.warning("sign-in with %s failed: %s", provider, type(exc).__name__)
        return _fail("provider")
    pid_hash = account_hash(provider, account)

    async with request.app.state.db.begin() as conn:
        user = (
            await conn.execute(
                text(
                    "SELECT id FROM users WHERE auth_provider = :p AND provider_user_id_hash = :h"
                ),
                {"p": provider, "h": pid_hash},
            )
        ).one_or_none()
        token = await _new_session(conn, user.id) if user else None

    if token:
        response = RedirectResponse("/signin/done", status.HTTP_303_SEE_OTHER)
        _session_cookie(response, token)
    else:
        ticket = secrets.token_urlsafe(32)
        await request.app.state.redis.set(
            f"oauth:signup:{ticket}",
            json.dumps({"provider": provider, "pid_hash": pid_hash}),
            ex=SIGNUP_SECONDS,
        )
        response = RedirectResponse("/signin/handle", status.HTTP_303_SEE_OTHER)
        _set_cookie(response, SIGNUP_COOKIE, ticket, SIGNUP_SECONDS, "strict")
    _clear_cookie(response, STATE_COOKIE)
    return response


TERMS_VERSION = "2026-11-06"


class SignupIn(BaseModel):
    model_config = {"extra": "forbid"}
    handle: str = Field(pattern=r"^[a-z0-9-]{3,30}$")
    accept_terms: Literal[True]
    terms_version: str


class AccessOut(BaseModel):
    access_token: str
    handle: str


@router.post("/signup")
async def signup(
    body: SignupIn,
    request: Request,
    response: Response,
    x_requested_with: Annotated[str | None, Header()] = None,
    ticket: Annotated[str | None, Cookie(alias=SIGNUP_COOKIE)] = None,
) -> AccessOut:
    """Create an account with a handle and consent."""
    _check_csrf(request, x_requested_with)
    await ratelimit.enforce(request, f"ratelimit:signup:{_client_ip(request)}", 20, 600)
    raw = await request.app.state.redis.get(f"oauth:signup:{ticket}") if ticket else None
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign-in expired, please start again")
    if body.terms_version != TERMS_VERSION:
        raise HTTPException(status.HTTP_409_CONFLICT, "The terms changed, please reload the page")
    if reserved_handle(body.handle) or body.handle.strip("-") != body.handle:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That handle is not allowed")
    pending = json.loads(raw)
    async with request.app.state.db.begin() as conn:
        taken = await conn.scalar(text("SELECT 1 FROM users WHERE handle = :h"), {"h": body.handle})
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT, "That handle is taken")
        user_id = await conn.scalar(
            text(
                "INSERT INTO users (handle, auth_provider, provider_user_id_hash,"
                " terms_version, terms_accepted_at)"
                " VALUES (:handle, :p, :h, :v, now())"
                " ON CONFLICT DO NOTHING RETURNING id"
            ),
            {
                "handle": body.handle,
                "p": pending["provider"],
                "h": pending["pid_hash"],
                "v": TERMS_VERSION,
            },
        )
        if user_id is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "That handle is taken")
        token = await _new_session(conn, user_id)
    await request.app.state.redis.delete(f"oauth:signup:{ticket}")
    _clear_cookie(response, SIGNUP_COOKIE)
    _session_cookie(response, token)
    return AccessOut(access_token=issue_token(user_id, body.handle), handle=body.handle)


@router.post("/refresh", response_model=AccessOut)
async def refresh(
    request: Request,
    response: Response,
    x_requested_with: Annotated[str | None, Header()] = None,
    token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> AccessOut | JSONResponse:
    """Rotates the session token."""
    _check_csrf(request, x_requested_with)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    async with request.app.state.db.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT s.id, s.family, s.used_at, s.revoked_at, s.expires_at > now() AS live,"
                    " u.id AS user_id, u.handle"
                    " FROM sessions s JOIN users u ON u.id = s.user_id"
                    " WHERE s.token_hash = :h FOR UPDATE OF s"
                ),
                {"h": _token_hash(token)},
            )
        ).one_or_none()
        new_token = None
        if row and row.revoked_at is None and row.live:
            if row.used_at is None:
                await conn.execute(
                    text("UPDATE sessions SET used_at = now() WHERE id = :id"), {"id": row.id}
                )
                new_token = await _new_session(conn, row.user_id, row.family)
            elif datetime.now(UTC) - row.used_at > REUSE_GRACE:
                log.warning("reused session token: family revoked")
                await conn.execute(
                    text(
                        "UPDATE sessions SET revoked_at = now()"
                        " WHERE family = :f AND revoked_at IS NULL"
                    ),
                    {"f": row.family},
                )
    if new_token is None or row is None:
        denied = JSONResponse({"detail": "Not signed in"}, status.HTTP_401_UNAUTHORIZED)
        _clear_cookie(denied, REFRESH_COOKIE)
        return denied
    _session_cookie(response, new_token)
    return AccessOut(access_token=issue_token(row.user_id, row.handle), handle=row.handle)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    x_requested_with: Annotated[str | None, Header()] = None,
    token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> None:
    """Sign out and end the session."""
    _check_csrf(request, x_requested_with)
    if token:
        async with request.app.state.db.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE sessions SET revoked_at = now() WHERE family ="
                    " (SELECT family FROM sessions WHERE token_hash = :h) AND revoked_at IS NULL"
                ),
                {"h": _token_hash(token)},
            )
    _clear_cookie(response, REFRESH_COOKIE)


@router.get("/providers")
async def providers() -> dict[str, bool]:
    """Which sign-in buttons to show."""
    s = get_settings()
    return {
        "github": bool(s.github_client_id and s.github_client_secret),
        "google": bool(s.google_client_id and s.google_client_secret),
    }
