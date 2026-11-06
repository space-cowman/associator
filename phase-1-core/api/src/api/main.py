"""FastAPI app: opens the Postgres pool and Redis client at startup, closes them at shutdown."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import boto3  # type: ignore[import-untyped]
import httpx
from botocore.config import Config as BotoConfig  # type: ignore[import-untyped]
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine

from api import activity
from api.config import get_settings
from api.routes import (
    chat,
    chat_ai,
    conversations,
    drafts,
    groups,
    health,
    me,
    memory,
    models,
    notifications,
    replies,
    reports,
    signin,
    threads,
    tokens,
    uploads,
    users,
    votes,
)

log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open and close the database, Redis and other clients."""
    settings = get_settings()
    app.state.db = create_async_engine(
        settings.database_url,
        pool_size=5,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )
    password = settings.redis_password.get_secret_value() if settings.redis_password else None
    app.state.redis = Redis.from_url(
        settings.redis_url, password=password, socket_timeout=5, decode_responses=True
    )
    app.state.safety = httpx.AsyncClient(base_url=settings.safety_url, timeout=15)
    app.state.gateway = httpx.AsyncClient(base_url=settings.llm_gateway_url, timeout=120)
    app.state.orchestrator = (
        httpx.AsyncClient(base_url=settings.orchestrator_url, timeout=180)
        if settings.orchestrator_url
        else None
    )
    app.state.oauth_http = httpx.AsyncClient(timeout=10, follow_redirects=False)
    app.state.kms = boto3.client("kms", region_name=settings.aws_region)
    app.state.s3 = boto3.client(
        "s3",
        region_name=settings.aws_region,
        endpoint_url=f"https://s3.{settings.aws_region}.amazonaws.com",
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )
    try:
        async with activity.running(app, settings.activity_metrics):
            yield
    finally:
        await app.state.gateway.aclose()
        if app.state.orchestrator is not None:
            await app.state.orchestrator.aclose()
        await app.state.oauth_http.aclose()
        await app.state.safety.aclose()
        await app.state.redis.aclose()
        await app.state.db.dispose()


def create_app() -> FastAPI:
    """Build the api app with all its routes."""
    docs = get_settings().docs_enabled
    app = FastAPI(
        title="platform-v2 api",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(groups.router)
    app.include_router(threads.router)
    app.include_router(replies.router)
    app.include_router(votes.router)
    app.include_router(models.router)
    app.include_router(memory.router)
    app.include_router(drafts.router)
    app.include_router(tokens.router)
    app.include_router(uploads.router)
    app.include_router(users.router)
    app.include_router(notifications.router)
    app.include_router(signin.router)
    app.include_router(conversations.router)
    app.include_router(chat.router)
    app.include_router(chat_ai.router)
    app.include_router(reports.router)

    @app.exception_handler(RequestValidationError)
    async def validation_errors(request: Request, exc: RequestValidationError) -> JSONResponse:
        """422 without echoing the rejected input: it may be a key or personal data."""
        errors = [{k: e[k] for k in ("type", "loc", "msg") if k in e} for e in exc.errors()]
        return JSONResponse({"detail": errors}, status_code=422)

    @app.middleware("http")
    async def internal_errors(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Unexpected error -> generic 500 in FastAPI's usual {"detail": ...} shape."""
        try:
            return await call_next(request)
        except Exception as exc:
            log.error("unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
            return JSONResponse({"detail": "Internal server error"}, status_code=500)

    return app


app = create_app()
