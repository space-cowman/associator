"""The orchestrator's metrics: fixed labels only, never text from the run."""

import asyncio

import pytest
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from orchestrator import telemetry

READER = InMemoryMetricReader()
metrics.set_meter_provider(MeterProvider(metric_readers=[READER]))


def _points() -> dict[str, list[dict[str, object]]]:
    """The recorded metric points."""
    data = READER.get_metrics_data()
    out: dict[str, list[dict[str, object]]] = {}
    for rm in data.resource_metrics if data else []:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                out[m.name] = [dict(p.attributes or {}) for p in m.data.data_points]
    return out


def test_a_split_run_is_counted_with_fixed_labels_only() -> None:
    """A split run is counted with fixed labels only."""
    final = {
        "parts": [{"kind": "code", "task": "SECRET TASK TEXT"}, {"kind": "explain", "task": "x"}],
        "writer": "merge",
        "status": "ready",
        "draft": "SECRET DRAFT TEXT",
        "models_used": ["a", "b", "a"],
        "fallback_used": True,
    }
    telemetry.run_finished(final, memory=True, seconds=2.5)
    points = _points()
    run = points["associator.orchestrator.runs"][-1]
    assert run == {
        "path": "split", "outcome": "ready", "reason": "", "memory": "on",
        "fallback": "yes", "models": "2",
    }  # fmt: skip
    assert {p["kind"] for p in points["associator.orchestrator.parts"]} == {"code", "explain"}
    assert "SECRET" not in repr(points)


def test_a_failed_single_run_keeps_its_reason() -> None:
    """A failed single run keeps its reason."""
    telemetry.run_finished({"status": "failed", "reason": "too_long"}, memory=False, seconds=1)
    runs = _points()["associator.orchestrator.runs"]
    assert {"path": "single", "outcome": "failed", "reason": "too_long", "memory": "off",
            "fallback": "no", "models": "0"} in runs  # fmt: skip


def test_timed_records_the_step_even_when_it_fails() -> None:
    """Timed records the step even when it fails."""

    @telemetry.timed("plan")
    async def boom() -> None:
        """A step that fails."""
        raise ValueError

    with pytest.raises(ValueError):
        asyncio.run(boom())
    assert {"step": "plan", "path": ""} in _points()["associator.orchestrator.step.duration"]
