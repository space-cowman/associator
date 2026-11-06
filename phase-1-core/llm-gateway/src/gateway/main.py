"""llm-gateway: the only service that talks to model providers."""

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Literal

import boto3  # type: ignore[import-untyped]
import httpx
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from gateway import evals, keys, privacy
from gateway.config import get_settings
from gateway.providers import (
    EMBED_MODELS,
    USER_BASE_URLS,
    FakeProvider,
    OpenAICompatible,
    Provider,
    ProviderError,
    same_model,
)
from gateway.telemetry import cost_usd, fallback, quota, record
from gateway.tracing import Tracer

log = logging.getLogger("gateway")

_calls = logging.getLogger("gateway.calls")
if not _calls.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _calls.addHandler(_handler)
    _calls.setLevel(logging.INFO)
    _calls.propagate = False

ERROR_STATUS = {
    "timeout": status.HTTP_504_GATEWAY_TIMEOUT,
    "rate_limited": status.HTTP_429_TOO_MANY_REQUESTS,
    "provider_error": status.HTTP_502_BAD_GATEWAY,
}


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class UserModel(BaseModel):
    """The caller's saved model, as stored by the api (ciphertext only; never a plain key)."""

    model_config = ConfigDict(extra="forbid")

    model_id: uuid.UUID
    provider: Literal["openrouter", "openai", "gemini", "anthropic"]
    model: str = Field(pattern=r"^[A-Za-z0-9._:/-]{2,100}$")
    key_ciphertext: str = Field(min_length=16, max_length=4096)


class CompleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^[A-Za-z0-9-]{8,64}$")
    user_id: uuid.UUID
    model: Literal["platform", "platform-small", "fake", "user"]
    system: str = Field(default="", max_length=10_000)
    messages: list[Message] = Field(min_length=1, max_length=20)
    max_tokens: int = Field(default=400, ge=16, le=2000)
    user_model: UserModel | None = None
    privacy: Literal["public", "private"] = "public"
    names: list[Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{3,30}$")]] = Field(
        default_factory=list, max_length=50
    )
    trace: Literal["off", "draft", "agent_draft", "chat_ai"] = "off"
    trace_shared: bool = False
    trace_messages: list[Message] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _user_model_iff_user(self) -> "CompleteIn":
        """A person's own model comes with its key, and only then."""
        if (self.model == "user") != (self.user_model is not None):
            raise ValueError("user_model is required for model 'user' and only for it")
        return self


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int


class CompleteOut(BaseModel):
    text: str
    provider: str
    model: str
    usage: Usage
    cost_usd: float
    duration_ms: int
    finish_reason: str
    trace_id: str | None = None


class EmbedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^[A-Za-z0-9-]{8,64}$")
    user_id: uuid.UUID
    user_model: UserModel
    texts: list[Annotated[str, StringConstraints(min_length=1, max_length=1000)]] = Field(
        min_length=1, max_length=100
    )


class EmbedOut(BaseModel):
    model: str
    vectors: list[list[float]]


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: uuid.UUID
    decision: Literal["approved", "edited", "discarded"]
    correction: str | None = Field(default=None, max_length=20_000)


def build_providers() -> dict[str, Provider]:
    """Set up the platform's model providers."""
    settings = get_settings()
    providers: dict[str, Provider] = {"fake": FakeProvider()}
    if settings.groq_api_key is not None:
        providers["platform"] = OpenAICompatible(
            "groq",
            settings.groq_base_url,
            settings.groq_api_key.get_secret_value(),
            settings.platform_model,
            options=(
                {"reasoning_effort": settings.platform_reasoning_effort}
                if settings.platform_reasoning_effort
                else None
            ),
        )
        providers["platform-small"] = OpenAICompatible(
            "groq",
            settings.groq_base_url,
            settings.groq_api_key.get_secret_value(),
            settings.platform_small_model,
        )
    return providers


def build_fallbacks() -> dict[str, list[Provider]]:
    """Platform AI only: who answers when its own model is rate limited."""
    settings = get_settings()
    if settings.groq_api_key is None or not settings.platform_fallback_model:
        return {}
    backup = OpenAICompatible(
        "groq",
        settings.groq_base_url,
        settings.groq_api_key.get_secret_value(),
        settings.platform_fallback_model,
        options=(
            {"reasoning_effort": settings.platform_reasoning_effort}
            if settings.platform_reasoning_effort
            else None
        ),
    )
    return {"platform": [backup]}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open and close the HTTP clients."""
    app.state.providers = build_providers()
    app.state.fallbacks = build_fallbacks()
    app.state.kms = boto3.client("kms", region_name=get_settings().aws_region)
    app.state.safety = httpx.AsyncClient(base_url=get_settings().safety_url, timeout=15)
    s = get_settings()
    app.state.tracer = (
        Tracer(s.langsmith_endpoint, s.langsmith_api_key.get_secret_value(), s.langsmith_project)
        if s.langsmith_api_key is not None
        else None
    )
    key = s.langsmith_api_key.get_secret_value() if s.langsmith_api_key is not None else None
    try:
        async with evals.running(s.langsmith_endpoint, key, s.langsmith_project):
            yield
    finally:
        await app.state.safety.aclose()


def create_app() -> FastAPI:
    """Build the gateway app with its routes."""
    docs = get_settings().docs_enabled
    app = FastAPI(
        title="platform-v2 llm-gateway",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )

    @app.middleware("http")
    async def internal_errors(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Unexpected error -> generic 500; logged as error type + path only."""
        try:
            return await call_next(request)
        except Exception as exc:
            log.error("unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
            return JSONResponse({"detail": "Internal server error"}, status_code=500)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Say the gateway is up."""
        return {"status": "ok"}

    @app.post("/complete")
    async def complete(body: CompleteIn, request: Request) -> CompleteOut:
        """Call a model, masking private content first."""
        provider: Provider | None
        if body.user_model is not None:
            provider = await _user_provider(request, body.user_id, body.user_model)
        else:
            provider = request.app.state.providers.get(body.model)
        if provider is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "model_unavailable")
        messages = [m.model_dump() for m in body.messages]
        sent_at = datetime.now(UTC)
        table: dict[str, str] = {}
        if body.privacy == "private":
            messages, table = await privacy.mask(request.app.state.safety, messages, body.names)
        kind = {"user": "user", "platform": "platform"}.get(body.model, "internal")

        def log_call(p: Provider, started: float, **result: int | str) -> None:
            """Record one model call without its text."""
            record(
                request_id=body.request_id,
                user_id=str(body.user_id),
                provider=p.name,
                model=p.model,
                kind=kind,
                duration_ms=int((time.monotonic() - started) * 1000),
                **result,  # type: ignore[arg-type]
            )

        chain = [provider]
        if body.user_model is None:
            chain += request.app.state.fallbacks.get(body.model, [])
        for attempt, p in enumerate(chain):
            started = time.monotonic()
            try:
                r = await p.complete(body.system, messages, body.max_tokens)
            except ProviderError as e:
                d = e.details
                if body.user_model is None:
                    quota(p.name, p.model, d.quota)
                log_call(
                    p,
                    started,
                    error=e.kind,
                    error_reason=e.reason,
                    error_message=d.message,
                    provider_http_status=d.http_status,
                    provider_error_code=d.error_code,
                    upstream=d.upstream,
                    limit_source=d.limit_source,
                )
                if e.kind == "rate_limited" and attempt + 1 < len(chain):
                    fallback(p.model, chain[attempt + 1].model, kind)
                    continue
                raise HTTPException(
                    ERROR_STATUS[e.kind],
                    {
                        "error": e.kind,
                        "reason": e.reason,
                        "upstream": d.upstream,
                        "retry_after": d.retry_after,
                    },
                ) from None
            provider = p
            break
        duration_ms = int((time.monotonic() - started) * 1000)
        if body.user_model is None:
            quota(provider.name, provider.model, r.quota)
        log_call(
            provider,
            started,
            input_tokens=r.input_tokens,
            output_tokens=r.output_tokens,
            finish_reason=r.finish_reason,
            response_model=r.response_model,
            response_id=r.response_id,
            upstream=r.upstream,
        )
        if body.user_model is not None and not same_model(provider.model, r.response_model):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "model_mismatch")
        cost = cost_usd(provider.name, provider.model, r.input_tokens, r.output_tokens)
        trace_id = None
        tracer: Tracer | None = request.app.state.tracer
        allowed = body.privacy == "public" or body.trace_shared
        if tracer is not None and body.trace != "off" and allowed:
            trace_id = await tracer.trace(
                request.app.state.safety,
                kind=body.trace,
                system=body.system,
                messages=[m.model_dump() for m in body.trace_messages]
                if body.trace_messages is not None
                else messages,
                answer=r.text,
                names=body.names,
                started=sent_at,
                metadata={
                    "model": provider.model,
                    "provider": provider.name,
                    "privacy": body.privacy,
                    "tokens_in": r.input_tokens,
                    "tokens_out": r.output_tokens,
                    "cost_usd": cost,
                    "duration_ms": duration_ms,
                },
            )
        return CompleteOut(
            text=privacy.restore(r.text, table),
            provider=provider.name,
            model=provider.model,
            usage=Usage(input_tokens=r.input_tokens, output_tokens=r.output_tokens),
            cost_usd=cost,
            duration_ms=duration_ms,
            finish_reason=r.finish_reason,
            trace_id=trace_id,
        )

    @app.post("/embed")
    async def embed(body: EmbedIn, request: Request) -> EmbedOut:
        """Memory search vectors with the person's own key."""
        name = EMBED_MODELS.get(body.user_model.provider)
        if name is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "no_embeddings")
        provider = await _user_provider(request, body.user_id, body.user_model)
        started = time.monotonic()
        try:
            vectors, tokens = await provider.embed(name, body.texts)
        except ProviderError as e:
            record(
                request_id=body.request_id,
                user_id=str(body.user_id),
                provider=provider.name,
                model=name,
                duration_ms=int((time.monotonic() - started) * 1000),
                error=e.kind,
                error_reason=e.reason,
                error_message=e.details.message,
                provider_http_status=e.details.http_status,
            )
            raise HTTPException(
                ERROR_STATUS[e.kind], {"error": e.kind, "reason": e.reason, "upstream": ""}
            ) from None
        record(
            request_id=body.request_id,
            user_id=str(body.user_id),
            provider=provider.name,
            model=name,
            duration_ms=int((time.monotonic() - started) * 1000),
            input_tokens=tokens,
        )
        return EmbedOut(model=name, vectors=vectors)

    @app.post("/feedback", status_code=status.HTTP_204_NO_CONTENT)
    async def feedback(body: FeedbackIn, request: Request) -> None:
        """A person's decision on a traced draft (approved 1, edited 0.5, discarded 0)."""
        tracer: Tracer | None = request.app.state.tracer
        if tracer is None:
            return
        try:
            await tracer.feedback(
                request.app.state.safety, body.trace_id, body.decision, body.correction
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("feedback not sent (%s)", type(exc).__name__)

    return app


async def _user_provider(request: Request, user_id: uuid.UUID, m: UserModel) -> OpenAICompatible:
    """Decrypt the user's key for this one call; the plaintext lives only in this client."""
    key_arn = get_settings().user_keys_kms_arn
    if key_arn is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "model_unavailable")
    key = await keys.decrypt(request.app.state.kms, key_arn, m.key_ciphertext, user_id, m.model_id)
    return OpenAICompatible(m.provider, USER_BASE_URLS[m.provider], key, m.model)


app = create_app()
