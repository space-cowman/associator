"""Prints a short-lived dev sign-in token."""

import asyncio
import hashlib
import sys
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from api.auth import TTL, issue_token
from api.config import get_settings

UPSERT = text(
    """
    INSERT INTO users (handle, auth_provider, provider_user_id_hash)
    VALUES (:handle, 'dev', :pid_hash)
    ON CONFLICT (auth_provider, provider_user_id_hash) DO UPDATE SET handle = users.handle
    RETURNING id, handle
    """
)


async def main(handle: str, actor: str, hours: int) -> None:
    """Print a dev sign-in token for a handle."""
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.begin() as conn:
            pid_hash = hashlib.sha256(f"dev:{handle}".encode()).hexdigest()
            row = (await conn.execute(UPSERT, {"handle": handle, "pid_hash": pid_hash})).one()
    finally:
        await engine.dispose()
    print(issue_token(row.id, row.handle, actor, timedelta(hours=hours) if hours else TTL))


if __name__ == "__main__":
    args = sys.argv[1:]
    hours = int(next((a.split("=", 1)[1] for a in args if a.startswith("--hours=")), "0"))
    flags = [a for a in args[1:] if not a.startswith("--hours=")]
    if not args or flags not in ([], ["--agent"]) or not 0 <= hours <= 12:
        sys.exit("usage: python -m api.dev_token <handle> [--agent] [--hours=1..12]")
    asyncio.run(main(args[0], "agent" if flags else "human", hours))
