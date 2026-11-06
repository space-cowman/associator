"""Activity and data-store numbers for the Grafana dashboards, refreshed every 5 minutes."""

import asyncio
import contextlib
import logging
from collections.abc import Iterable
from typing import Any

from fastapi import FastAPI
from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation
from sqlalchemy import text

log = logging.getLogger("api.activity")
REFRESH_SECONDS = 300

_LAST_24H = """
WITH since AS (SELECT now() - interval '24 hours' AS t)
SELECT 'people', 'active', count(DISTINCT who) FROM (
    SELECT author_id AS who FROM threads, since WHERE created_at > since.t
    UNION ALL SELECT author_id FROM replies, since WHERE created_at > since.t
    UNION ALL SELECT voter_id FROM votes, since WHERE created_at > since.t
    UNION ALL SELECT voter_id FROM thread_votes, since WHERE created_at > since.t
    UNION ALL SELECT user_id FROM drafts, since WHERE created_at > since.t
) AS a
UNION ALL SELECT 'people', 'signups', count(*) FROM users, since WHERE created_at > since.t
UNION ALL SELECT 'threads', CASE WHEN by_agent THEN 'mcp' ELSE 'person' END, count(*)
    FROM threads, since WHERE created_at > since.t GROUP BY 2
UNION ALL SELECT 'replies', mode, count(*) FROM replies, since WHERE created_at > since.t
    GROUP BY 2
UNION ALL SELECT 'votes', voter_type, count(*) FROM (
    SELECT voter_type, created_at FROM votes
    UNION ALL SELECT voter_type, created_at FROM thread_votes
) AS v, since WHERE created_at > since.t GROUP BY 2
UNION ALL SELECT 'drafts', mode, count(*) FROM drafts, since WHERE created_at > since.t
    GROUP BY 2
UNION ALL SELECT 'cluster_joins', '', count(*) FROM group_members, since
    WHERE joined_at > since.t
UNION ALL SELECT 'clusters', 'new', count(*) FROM topic_groups, since WHERE created_at > since.t
UNION ALL SELECT 'chat', 'messages', count(*) FROM chat_messages, since
    WHERE created_at > since.t AND kind = 'text'
UNION ALL SELECT 'chat', 'conversations', count(*) FROM conversations, since
    WHERE created_at > since.t
"""

_TOTAL = """
SELECT 'people', '', count(*) FROM users
UNION ALL SELECT 'threads', '', count(*) FROM threads WHERE deleted_at IS NULL
UNION ALL SELECT 'threads', 'satisfied', count(*) FROM threads
    WHERE deleted_at IS NULL AND satisfied_reply_id IS NOT NULL
UNION ALL SELECT 'replies', '', count(*) FROM replies
UNION ALL SELECT 'clusters', '', count(*) FROM topic_groups
UNION ALL SELECT 'memory_items', '', count(*) FROM memory_items
UNION ALL SELECT 'memory_people', '', count(DISTINCT user_id) FROM memory_items
UNION ALL SELECT 'saved_models', '', count(*) FROM model_registry
UNION ALL SELECT 'people_with_models', CAST(n AS text), count(*) FROM (
    SELECT count(*) AS n FROM model_registry WHERE enabled GROUP BY user_id
) AS m GROUP BY n
"""

_POSTGRES = """
SELECT numbackends, xact_commit, xact_rollback, blks_hit, blks_read, deadlocks,
       pg_database_size(current_database())
FROM pg_stat_database WHERE datname = current_database()
"""

_numbers: dict[str, dict[tuple[str, str], float]] = {"last_24h": {}, "total": {}, "store": {}}


def _gauge(name: str) -> Any:
    """Register one activity gauge that reads the latest counts."""

    def callback(options: CallbackOptions) -> Iterable[Observation]:
        """Report the stored counts for this gauge."""
        for (a, b), value in list(_numbers[name].items()):
            if name == "store":
                yield Observation(value, {"store": a, "stat": b})
            else:
                yield Observation(value, {"feature": a, "kind": b})

    return callback


_meter = metrics.get_meter("associator.api")
_meter.create_observable_gauge(
    "associator.activity.last_24h",
    callbacks=[_gauge("last_24h")],
    description="What people did in the last 24 hours, per feature",
)
_meter.create_observable_gauge(
    "associator.activity.total", callbacks=[_gauge("total")], description="Totals so far"
)
_meter.create_observable_gauge(
    "associator.datastore",
    callbacks=[_gauge("store")],
    description="Postgres and Redis health (connections, size, cache hits, memory)",
)


async def refresh(app: FastAPI) -> None:
    """Count activity in the database and remember the numbers."""
    async with app.state.db.connect() as conn:
        last = (await conn.execute(text(_LAST_24H))).all()
        total = (await conn.execute(text(_TOTAL))).all()
        pg = (await conn.execute(text(_POSTGRES))).one()
    _numbers["last_24h"] = {(f, k or ""): float(n) for f, k, n in last}
    _numbers["total"] = {(f, k or ""): float(n) for f, k, n in total}
    backends, commits, rollbacks, hit, read, deadlocks, size = pg
    store: dict[tuple[str, str], float] = {
        ("postgres", "connections"): backends,
        ("postgres", "commits"): commits,
        ("postgres", "rollbacks"): rollbacks,
        ("postgres", "deadlocks"): deadlocks,
        ("postgres", "size_bytes"): size,
        ("postgres", "cache_hit_ratio"): hit / (hit + read) if hit + read else 1.0,
    }
    try:
        store[("redis", "keys")] = await app.state.redis.dbsize()
    except Exception as exc:  # noqa: BLE001
        log.warning("redis size failed (%s)", type(exc).__name__)
    _numbers["store"] = store


async def _forever(app: FastAPI) -> None:
    """Refresh the counts every few minutes until the app stops."""
    while True:
        try:
            await refresh(app)
        except Exception as exc:  # noqa: BLE001
            log.warning("activity refresh failed (%s)", type(exc).__name__)
        await asyncio.sleep(REFRESH_SECONDS)


@contextlib.asynccontextmanager
async def running(app: FastAPI, enabled: bool) -> Any:
    """Start the activity counter while the app runs, if enabled."""
    task = asyncio.create_task(_forever(app)) if enabled else None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
