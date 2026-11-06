"""Counts and timings (OpenTelemetry), shown on the Grafana AI dashboard."""

import functools
import time
from collections.abc import Callable, Coroutine, Iterable
from typing import Any

from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation

_meter = metrics.get_meter("associator.orchestrator")

_runs = _meter.create_counter(
    "associator.orchestrator.runs", description="Ask my AI runs by path and result"
)
_parts = _meter.create_counter("associator.orchestrator.parts", description="Planned parts")
_tries = _meter.create_counter(
    "associator.orchestrator.model_tries", description="Model calls tried, by who and result"
)
_decisions = _meter.create_counter(
    "associator.orchestrator.decisions", description="What people decided on a run's draft"
)


def _up(options: CallbackOptions) -> Iterable[Observation]:
    """Report that the orchestrator is running."""
    yield Observation(1)


_meter.create_observable_gauge("associator.orchestrator.up", callbacks=[_up], description="1")
_steps = _meter.create_histogram(
    "associator.orchestrator.step.duration",
    unit="s",
    description="Time spent in each step of the graph",
    explicit_bucket_boundaries_advisory=[0.5, 1, 2, 3, 5, 8, 13, 20, 30, 60],
)


def run_finished(final: dict[str, Any], *, memory: bool, seconds: float) -> None:
    """path: single (one model answered) or split (planned, several models, merged)."""
    split = final.get("writer") == "merge" or bool(final.get("parts"))
    ready = final.get("status") == "ready"
    labels = {
        "path": "split" if split else "single",
        "outcome": "ready" if ready else "failed",
        "reason": "" if ready else str(final.get("reason", "failed")),
        "memory": "on" if memory else "off",
        "fallback": "yes" if final.get("fallback_used") else "no",
        "models": str(len(set(final.get("models_used", [])))),
    }
    _runs.add(1, labels)
    _steps.record(seconds, {"step": "total", "path": labels["path"]})
    for part in final.get("parts", []):
        _parts.add(1, {"kind": part["kind"]})


def model_try(*, own: bool, ok: bool, reason: str = "") -> None:
    """own: one of the person's models (else Platform AI); reason: the gateway's cause."""
    _tries.add(1, {"who": "own" if own else "platform", "outcome": "ok" if ok else reason})


def decided(decision: str) -> None:
    """Count a draft decision."""
    _decisions.add(1, {"decision": decision})


def timed[**P, R](
    step: str,
) -> Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]:
    """Time a graph node."""

    def wrap(node: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        """Time a graph step."""

        @functools.wraps(node)
        async def inner(*args: P.args, **kwargs: P.kwargs) -> R:
            """Run the step and record its time."""
            start = time.perf_counter()
            try:
                return await node(*args, **kwargs)
            finally:
                _steps.record(time.perf_counter() - start, {"step": step, "path": ""})

        return inner

    return wrap
