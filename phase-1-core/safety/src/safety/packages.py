"""Fake or mistyped package check: install commands in code are looked up on PyPI / npm."""

import asyncio
import re
import shlex
import time
from urllib.parse import quote

import httpx

from safety.config import get_settings

MAX_LOOKUPS = 10
CACHE_SECONDS = 24 * 3600
CACHE_MAX = 5_000

_INSTALL = re.compile(
    r"\b(?P<tool>pip3?|uv\s+pip|uv|poetry|pipx|npm|pnpm|yarn)\s+(?:install|add|i)\b(?P<args>[^\n;&|#]*)"
)
_PYPI_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?$")
_NPM_NAME = re.compile(r"^(?:@[a-z0-9][a-z0-9._~-]*/)?[a-z0-9][a-z0-9._~-]{0,213}$")
_VERSION = re.compile(r"(?:\[.*?\])?(?:[=<>!~^@].*)?$")

_cache: dict[tuple[str, str], tuple[float, bool]] = {}


_FLAGS_WITH_VALUE = {
    "-r",
    "-c",
    "-e",
    "-i",
    "-f",
    "--requirement",
    "--constraint",
    "--editable",
    "--index-url",
    "--extra-index-url",
    "--find-links",
}


def _package_name(token: str, registry: str) -> str | None:
    """Bare package name from an install argument, or None for flags, paths and URLs."""
    if token.startswith(("-", ".", "/", "~")) or "://" in token or token.startswith("git+"):
        return None
    if registry == "npm":
        if token.startswith("@"):
            name = "@" + token[1:].partition("@")[0]
        elif "/" in token:
            return None
        else:
            name = token.partition("@")[0]
        return name if _NPM_NAME.fullmatch(name) else None
    name = _VERSION.sub("", token)
    return name if _PYPI_NAME.fullmatch(name) else None


def install_targets(code: str) -> list[tuple[str, str, int, int]]:
    """(registry, name, start, end) for packages named in install commands."""
    found: list[tuple[str, str, int, int]] = []
    for m in _INSTALL.finditer(code):
        registry = "npm" if m["tool"] in ("npm", "pnpm", "yarn") else "pypi"
        try:
            tokens = shlex.split(m["args"])
        except ValueError:
            continue
        skip_next = False
        for token in tokens:
            if skip_next:
                skip_next = False
            elif token in _FLAGS_WITH_VALUE:
                skip_next = True
            elif name := _package_name(token, registry):
                at = code.find(token, m.start("args"))
                found.append((registry, name, at, at + len(token)))
    return found[:MAX_LOOKUPS]


async def _exists(client: httpx.AsyncClient, registry: str, name: str) -> bool | None:
    """Whether a package exists in its registry."""
    key = (registry, name.lower())
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]
    url = (
        f"https://pypi.org/pypi/{quote(name, safe='')}/json"
        if registry == "pypi"
        else f"https://registry.npmjs.org/{quote(name, safe='@')}"
    )
    try:
        response = await client.get(url)
    except httpx.HTTPError:
        return None
    if response.status_code not in (200, 404):
        return None
    exists = response.status_code == 200
    if len(_cache) >= CACHE_MAX:
        _cache.clear()
    _cache[key] = (time.monotonic(), exists)
    return exists


async def find_missing(code: str) -> list[tuple[str, int, int]]:
    """(label, start, end) for each install target that does not exist on its registry."""
    settings = get_settings()
    targets = install_targets(code)
    if not settings.package_lookup or not targets:
        return []
    async with httpx.AsyncClient(
        timeout=settings.package_lookup_timeout_seconds, follow_redirects=False
    ) as client:
        results = await asyncio.gather(*(_exists(client, reg, name) for reg, name, _, _ in targets))
    return [
        (f"{'PyPI' if reg == 'pypi' else 'npm'} package '{name}' not found", start, end)
        for (reg, name, start, end), exists in zip(targets, results, strict=True)
        if exists is False
    ]
