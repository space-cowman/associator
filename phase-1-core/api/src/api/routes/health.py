"""Liveness (/healthz) and readiness (/readyz) for Kubernetes probes."""

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """The process is up."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request, response: Response) -> dict[str, str]:
    """Ready to serve traffic: Postgres and Redis both answer."""
    checks = {"postgres": "ok", "redis": "ok"}
    try:
        async with request.app.state.db.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        checks["postgres"] = "unavailable"
    try:
        await request.app.state.redis.ping()
    except Exception:
        checks["redis"] = "unavailable"
    if "unavailable" in checks.values():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}
    return {"status": "ok"}
