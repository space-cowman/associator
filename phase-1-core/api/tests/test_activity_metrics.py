"""Activity gauges and the draft path label: counts with fixed labels only."""

import uuid

import pytest
from opentelemetry.metrics import CallbackOptions

from api import activity, metrics


@pytest.mark.parametrize(
    ("run_id", "plan", "path"),
    [
        (None, [], "direct"),
        (uuid.uuid4(), [], "single"),
        (uuid.uuid4(), [{"kind": "code"}], "single"),
        (uuid.uuid4(), [{"kind": "code"}, {"kind": "explain"}], "split"),
        (uuid.uuid4(), None, "single"),
    ],
)
def test_draft_path(run_id: object, plan: object, path: str) -> None:
    """Draft path."""
    assert metrics.draft_path(run_id, plan) == path


def test_gauges_report_the_last_refresh() -> None:
    """Gauges report the last refresh."""
    activity._numbers["last_24h"] = {("replies", "ask_my_ai"): 3.0}
    activity._numbers["store"] = {("postgres", "connections"): 8.0}
    seen = list(activity._gauge("last_24h")(CallbackOptions()))
    assert [(o.value, o.attributes) for o in seen] == [
        (3.0, {"feature": "replies", "kind": "ask_my_ai"})
    ]
    store = list(activity._gauge("store")(CallbackOptions()))
    assert store[0].attributes == {"store": "postgres", "stat": "connections"}
