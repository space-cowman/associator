"""LangSmith judge numbers: parsed from feedback_stats, aggregates only."""

import asyncio
import json

import httpx

from gateway import evals

STATS = {
    "answer_relevance": {"n": 58, "avg": 0.75, "errors": 17, "values": {}},
    "pii_leak": {"n": 58, "avg": 0, "errors": 40, "values": {}},
    "human_decision": {"n": 35, "avg": 0.54, "errors": 0,
                       "values": {"approved": 18, "discarded": 15, "edited": 2}},
    "broken": "not a dict",
}  # fmt: skip


def test_numbers_from_feedback_stats() -> None:
    """Numbers from feedback stats."""
    out = evals.numbers_from(STATS, "7d")
    assert out[("answer_relevance", "scored", "7d")] == 41
    assert out[("answer_relevance", "errors", "7d")] == 17
    assert out[("answer_relevance", "avg", "7d")] == 0.75
    assert out[("pii_leak", "avg", "7d")] == 0
    assert out[("human_decision", "approved", "7d")] == 18
    assert not any(k[0] == "broken" for k in out)


def test_refresh_reads_both_windows_and_only_stats() -> None:
    """Refresh reads both windows and only stats."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Answer like LangSmith and record the request."""
        seen.append(request.url.path)
        if request.url.path == "/api/v1/sessions":
            return httpx.Response(200, json=[{"id": "p1"}])
        body = json.loads(request.content)
        assert body["session"] == ["p1"] and body["is_root"] is True
        return httpx.Response(200, json={"feedback_stats": STATS})

    async def go() -> None:
        """Run one refresh."""
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://ls.test"
        ) as c:
            await evals.refresh(c, "associator-drafts")

    asyncio.run(go())
    assert seen == ["/api/v1/sessions", "/api/v1/runs/stats", "/api/v1/runs/stats"]
    assert evals._numbers[("answer_relevance", "scored", "24h")] == 41
    assert evals._numbers[("human_decision", "edited", "7d")] == 2
