"""Masked traces of AI drafts to LangSmith, and people's decisions as feedback on them."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi.concurrency import run_in_threadpool
from langsmith import Client

from gateway import privacy

log = logging.getLogger("gateway.tracing")

SCORES = {"approved": 1.0, "edited": 0.5, "discarded": 0.0}


class Tracer:
    def __init__(self, endpoint: str, api_key: str, project: str) -> None:
        """Set up LangSmith tracing."""
        self.client = Client(api_url=endpoint, api_key=api_key, auto_batch_tracing=True)
        self.project = project

    async def trace(
        self,
        safety: httpx.AsyncClient,
        *,
        kind: str,
        system: str,
        messages: list[dict[str, str]],
        answer: str,
        started: datetime,
        metadata: dict[str, Any],
        names: list[str] | None = None,
    ) -> str | None:
        """Send a masked trace of a call to LangSmith."""
        try:
            masked, _ = await privacy.mask(
                safety, [*messages, {"role": "assistant", "content": answer}], names or []
            )
            run_id = uuid.uuid4()
            await run_in_threadpool(
                self.client.create_run,
                id=run_id,
                name=kind,
                run_type="llm",
                project_name=self.project,
                inputs={"system": system, "messages": masked[:-1]},
                outputs={"answer": masked[-1]["content"]},
                extra={"metadata": metadata},
                start_time=started,
                end_time=datetime.now(UTC),
            )
            return str(run_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("trace not sent (%s)", type(exc).__name__)
            return None

    async def feedback(
        self,
        safety: httpx.AsyncClient,
        trace_id: uuid.UUID,
        decision: str,
        correction: str | None = None,
    ) -> None:
        """Send a person's decision on a draft as feedback."""
        fixed = None
        if correction:
            masked, _ = await privacy.mask(safety, [{"role": "user", "content": correction}], [])
            fixed = {"answer": masked[0]["content"]}
        await run_in_threadpool(
            self.client.create_feedback,
            run_id=trace_id,
            key="human_decision",
            score=SCORES[decision],
            value=decision,
            correction=fixed,
        )
