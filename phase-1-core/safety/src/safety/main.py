"""Safety service: deterministic checks on posts, replies and drafts."""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from safety.checks import package_checks, report, run_checks
from safety.config import get_settings
from safety.mask import Masker
from safety.models import CheckIn, MaskIn, MaskOut, SafetyReport
from safety.pii import engine

log = logging.getLogger("safety")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load the language model and open clients."""
    await run_in_threadpool(engine)
    yield


def create_app() -> FastAPI:
    """Build the safety app with its routes."""
    docs = get_settings().docs_enabled
    app = FastAPI(
        title="platform-v2 safety",
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
        """Unexpected error -> generic 500; logged as error type + path only (never the text)."""
        try:
            return await call_next(request)
        except Exception as exc:
            log.error("unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
            return JSONResponse({"detail": "Internal server error"}, status_code=500)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Say the safety service is up."""
        return {"status": "ok"}

    @app.post("/mask")
    async def mask(body: MaskIn) -> MaskOut:
        """Replace personal data with placeholders."""

        def run() -> MaskOut:
            """Mask the texts."""
            masker = Masker()
            texts = [masker.mask(t, body.names) for t in body.texts]
            return MaskOut(texts=texts, table=masker.table, secrets_removed=masker.secrets_removed)

        return await run_in_threadpool(run)

    @app.post("/check")
    async def check(body: CheckIn) -> SafetyReport:
        """Check a post for keys, personal data and limits."""
        scanned, packages = await asyncio.gather(
            run_in_threadpool(run_checks, body), package_checks(body)
        )
        return report(scanned + packages)

    return app


app = create_app()
