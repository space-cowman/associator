"""orchestrator: Ask my AI as a LangGraph flow (Phase 2)."""

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from orchestrator import graph, telemetry
from orchestrator.config import Settings, get_settings
from orchestrator.contract import Part, ResumeIn, RunIn, RunOut

log = logging.getLogger("orchestrator")
SWEEP_SECONDS = 3600


def _config(run_id: uuid.UUID) -> dict[str, dict[str, str]]:
    """The graph settings for one run."""
    return {"configurable": {"thread_id": str(run_id)}}


@asynccontextmanager
async def _saver(settings: Settings) -> AsyncIterator[BaseCheckpointSaver[str]]:
    """Postgres when a password is configured, otherwise in memory (tests, local runs)."""
    if settings.postgres_password is None:
        yield InMemorySaver()
        return
    conninfo = (
        f"host={settings.postgres_host} port={settings.postgres_port}"
        f" dbname={settings.postgres_db} user={settings.postgres_user}"
    )
    async with AsyncConnectionPool(
        conninfo,
        min_size=1,
        max_size=4,
        open=False,
        kwargs={
            "password": settings.postgres_password.get_secret_value(),
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
    ) as pool:
        saver = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await saver.setup()
        yield saver


async def sweep(saver: BaseCheckpointSaver[str], older_than: timedelta) -> int:
    """Delete runs whose newest save is older than `older_than` (nobody decided on them)."""
    newest: dict[str, datetime] = {}
    async for t in saver.alist(None):
        thread = str(t.config["configurable"]["thread_id"])
        at = datetime.fromisoformat(t.checkpoint["ts"])
        newest[thread] = max(at, newest.get(thread, at))
    cutoff = datetime.now(UTC) - older_than
    old = [thread for thread, at in newest.items() if at < cutoff]
    for thread in old:
        await saver.adelete_thread(thread)
    return len(old)


async def _sweep_forever(saver: BaseCheckpointSaver[str], days: int) -> None:
    """Delete old runs every hour."""
    while True:
        try:
            if removed := await sweep(saver, timedelta(days=days)):
                log.info("deleted %d undecided run(s)", removed)
        except Exception as exc:  # noqa: BLE001
            log.warning("sweep failed (%s)", type(exc).__name__)
        await asyncio.sleep(SWEEP_SECONDS)


def _out(run_id: uuid.UUID, final: graph.State) -> RunOut:
    """Shape a run's result."""
    answers = {a["index"]: a for a in final.get("answers", [])}
    plan = [
        Part(kind=p["kind"], task=p["task"], model=answers[n]["model"] if n in answers else None)
        for n, p in enumerate(final.get("parts", []))
    ]
    ready = final.get("status") == "ready"
    return RunOut(
        run_id=run_id,
        status="ready" if ready else "failed",
        text=final.get("draft") if ready else None,
        reason=None if ready else final.get("reason", "failed"),
        plan=plan,
        models_used=list(dict.fromkeys(final.get("models_used", []))),
        fallback_used=final.get("fallback_used", False),
        trace_ids=final.get("trace_ids", []),
    )


def create_app(checkpointer: BaseCheckpointSaver[str] | None = None) -> FastAPI:
    """`checkpointer`: tests pass one to share saved runs across app instances (a restart)."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Open and close the checkpointer and clients."""
        app.state.gateway = httpx.AsyncClient(
            base_url=settings.gateway_url, timeout=settings.gateway_timeout_seconds
        )
        async with contextlib.AsyncExitStack() as stack:
            if checkpointer is None:
                saver = await stack.enter_async_context(_saver(settings))
            else:
                saver = checkpointer
            app.state.saver = saver
            app.state.graph = graph.build(saver)
            sweeper = asyncio.create_task(_sweep_forever(saver, settings.run_retention_days))
            try:
                yield
            finally:
                sweeper.cancel()
                await app.state.gateway.aclose()

    app = FastAPI(
        title="platform-v2 orchestrator",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Say the orchestrator is up."""
        return {"status": "ok"}

    @app.post("/runs")
    async def start_run(body: RunIn, request: Request) -> RunOut:
        """Plan, ask the person's models, merge, check; a ready draft waits for approval."""
        run_id = uuid.uuid4()
        start = time.perf_counter()
        final = await request.app.state.graph.ainvoke(
            {},
            _config(run_id),
            context=graph.Context(run=body, client=request.app.state.gateway),
        )
        telemetry.run_finished(final, memory=bool(body.memory), seconds=time.perf_counter() - start)
        if final.get("status") != "ready":
            await request.app.state.saver.adelete_thread(str(run_id))
        return _out(run_id, final)

    @app.get("/runs/{run_id}")
    async def get_run(run_id: uuid.UUID, request: Request) -> RunOut:
        """A run waiting for the person's decision (also after a restart)."""
        snapshot = await request.app.state.graph.aget_state(_config(run_id))
        if not snapshot.values or not snapshot.next:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such run waiting")
        return _out(run_id, snapshot.values)

    @app.post("/runs/{run_id}/resume", status_code=status.HTTP_204_NO_CONTENT)
    async def resume_run(run_id: uuid.UUID, body: ResumeIn, request: Request) -> None:
        """The person approved, edited or discarded the draft: finish the run, then delete it."""
        config = _config(run_id)
        snapshot = await request.app.state.graph.aget_state(config)
        if not snapshot.next:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such run waiting")
        await request.app.state.graph.ainvoke(Command(resume=body.decision), config)
        await request.app.state.saver.adelete_thread(str(run_id))
        telemetry.decided(body.decision)

    return app


app = create_app()
