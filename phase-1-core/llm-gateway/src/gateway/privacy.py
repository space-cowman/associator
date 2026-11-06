"""Masks private content before it reaches a model, and restores the answer."""

import re

import httpx
from fastapi import HTTPException, status


async def mask(
    client: httpx.AsyncClient, messages: list[dict[str, str]], names: list[str]
) -> tuple[list[dict[str, str]], dict[str, str]]:
    """Messages with personal data replaced by placeholders, and the table to restore them."""
    try:
        r = await client.post(
            "/mask", json={"texts": [m["content"] for m in messages], "names": names}
        )
        r.raise_for_status()
        out = r.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "privacy_unavailable") from None
    masked = [{**m, "content": text} for m, text in zip(messages, out["texts"], strict=True)]
    return masked, dict(out["table"])


def restore(text: str, table: dict[str, str]) -> str:
    """Put the real values back into the answer."""
    if not table:
        return text
    pattern = re.compile("|".join(re.escape(token) for token in table))
    return pattern.sub(lambda m: table[m.group(0)], text)
