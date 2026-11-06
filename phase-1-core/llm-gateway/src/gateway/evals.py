"""LangSmith judge scores as Grafana numbers, refreshed every 15 minutes."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation

log = logging.getLogger("gateway.evals")
REFRESH_SECONDS = 900
WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7)}

_numbers: dict[tuple[str, str, str], float] = {}


def _observe(options: CallbackOptions) -> Iterable[Observation]:
    """Report the latest judge scores."""
    for (judge, stat, window), value in list(_numbers.items()):
        yield Observation(value, {"judge": judge, "stat": stat, "window": window})


metrics.get_meter("associator.gateway").create_observable_gauge(
    "associator.evals.feedback",
    callbacks=[_observe],
    description="LangSmith feedback on drafts: judge averages, scored and failed counts, decisions",
)


def numbers_from(stats: dict[str, Any], window: str) -> dict[tuple[str, str, str], float]:
    """LangSmith's feedback_stats -> (judge, stat, window): avg, scored, errors (+ decisions)."""
    out: dict[tuple[str, str, str], float] = {}
    for judge, s in (stats or {}).items():
        if not isinstance(s, dict):
            continue
        n, errors = int(s.get("n") or 0), int(s.get("errors") or 0)
        out[(judge, "scored", window)] = max(n - errors, 0)
        out[(judge, "errors", window)] = errors
        if s.get("avg") is not None:
            out[(judge, "avg", window)] = float(s["avg"])
        for value, count in (s.get("values") or {}).items():
            out[(judge, str(value), window)] = float(count)
    return out


async def refresh(client: httpx.AsyncClient, project: str) -> None:
    """Read the judge scores from LangSmith."""
    found = (await client.get("/api/v1/sessions", params={"name": project})).json()
    if not found:
        return
    fresh: dict[tuple[str, str, str], float] = {}
    for window, span in WINDOWS.items():
        since = (datetime.now(UTC) - span).isoformat()
        r = await client.post(
            "/api/v1/runs/stats",
            json={"session": [found[0]["id"]], "start_time": since, "is_root": True},
        )
        r.raise_for_status()
        fresh.update(numbers_from(r.json().get("feedback_stats") or {}, window))
    _numbers.clear()
    _numbers.update(fresh)


async def _forever(client: httpx.AsyncClient, project: str) -> None:
    """Refresh the judge scores every few minutes."""
    while True:
        try:
            await refresh(client, project)
        except Exception as exc:  # noqa: BLE001
            log.warning("evals refresh failed (%s)", type(exc).__name__)
        await asyncio.sleep(REFRESH_SECONDS)


@contextlib.asynccontextmanager
async def running(endpoint: str, api_key: str | None, project: str) -> AsyncIterator[None]:
    """No LangSmith key (tests, local runs): nothing runs."""
    if api_key is None:
        yield
        return
    async with httpx.AsyncClient(
        base_url=endpoint, headers={"x-api-key": api_key}, timeout=30
    ) as client:
        task = asyncio.create_task(_forever(client, project))
        try:
            yield
        finally:
            task.cancel()
