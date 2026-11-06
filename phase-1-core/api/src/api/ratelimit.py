"""Per-key fixed-window rate limit in Redis."""

from fastapi import HTTPException, Request, status


async def enforce(
    request: Request,
    key: str,
    limit: int,
    window_seconds: int,
    message: str = "Too many requests, try again later",
) -> None:
    """Refuse the request when the person is over the limit."""
    redis = request.app.state.redis
    async with redis.pipeline(transaction=True) as pipe:
        count, _ = await pipe.incr(key).expire(key, window_seconds, nx=True).execute()
    if count > limit:
        ttl = await redis.ttl(key)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            message,
            headers={"Retry-After": str(max(ttl, 1))},
        )
