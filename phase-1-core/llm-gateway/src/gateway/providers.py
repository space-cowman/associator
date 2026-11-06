"""Model providers."""

from dataclasses import dataclass, field
from typing import Any, Protocol

import openai

from gateway.scrub import scrub


@dataclass(frozen=True)
class Result:
    text: str
    input_tokens: int
    output_tokens: int
    finish_reason: str
    response_model: str = ""
    response_id: str = ""
    upstream: str = ""
    quota: dict[str, int] = field(default_factory=dict)


@dataclass
class ErrorDetails:
    """Everything the provider said about a failure, already scrubbed (no keys, no prompts)."""

    message: str = ""
    http_status: int = 0
    error_code: str = ""
    upstream: str = ""
    limit_source: str = ""
    extra: dict[str, str] = field(default_factory=dict)
    quota: dict[str, int] = field(default_factory=dict)
    retry_after: float = 0.0


class ProviderError(Exception):
    """kind: "timeout", "rate_limited" or "provider_error"; reason: a finer, user-facing cause."""

    def __init__(self, kind: str, reason: str = "", details: ErrorDetails | None = None) -> None:
        """Keep the kind and cause of a failure."""
        super().__init__(kind)
        self.kind = kind
        self.reason = reason or kind
        self.details = details or ErrorDetails()


QUOTA_HEADERS = {
    "x-ratelimit-limit-requests": "requests_limit",
    "x-ratelimit-remaining-requests": "requests_remaining",
    "x-ratelimit-limit-tokens": "tokens_limit",
    "x-ratelimit-remaining-tokens": "tokens_remaining",
}


def quota_from(headers: Any) -> dict[str, int]:
    """The provider's quota numbers from a response's headers (missing or odd values skipped)."""
    out: dict[str, int] = {}
    for header, name in QUOTA_HEADERS.items():
        value = headers.get(header) if headers is not None else None
        if value is not None and str(value).isdigit():
            out[name] = int(value)
    return out


def _seconds(value: object) -> float:
    """Read a wait time in seconds from a header."""
    try:
        return max(0.0, float(str(value)))
    except ValueError:
        return 0.0


def _reason(status: int, limit_source: str) -> str:
    """Name the cause of a failed call."""
    if status == 429:
        return "upstream_busy" if limit_source.startswith("upstream") else "quota_exhausted"
    return {
        401: "invalid_key",
        403: "not_allowed",
        402: "insufficient_credits",
        404: "model_unavailable",
    }.get(status, "provider_error")


class Provider(Protocol):
    name: str
    model: str

    async def complete(
        self, system: str, messages: list[dict[str, str]], max_tokens: int
    ) -> Result:
        """Get an answer from the model."""
        ...


class FakeProvider:
    """Fixed answer, no key, no cost: for tests."""

    name, model = "fake", "fake-1"

    async def complete(
        self, system: str, messages: list[dict[str, str]], max_tokens: int
    ) -> Result:
        """Answer with fixed test text."""
        return Result("This is a fake answer for tests.", 10, 7, "stop", "fake-1")


class OpenAICompatible:
    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        http_client: Any = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        """Set up a provider with an OpenAI-style API."""
        self.name, self.model = name, model
        self._key = api_key
        self._options = options or {}
        self._client = openai.AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=30,
            max_retries=0,
            http_client=http_client,
        )

    async def complete(
        self, system: str, messages: list[dict[str, str]], max_tokens: int
    ) -> Result:
        """Get an answer from the model."""
        try:
            raw = await self._client.chat.completions.with_raw_response.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, *messages],  # type: ignore[list-item]
                max_tokens=max_tokens,
                extra_body=self._options or None,
            )
        except openai.APIError as e:
            raise self._error(e, (system, *(m["content"] for m in messages))) from None
        r = raw.parse()
        choice = r.choices[0]
        extra = r.model_extra or {}
        return Result(
            text=choice.message.content or "",
            input_tokens=r.usage.prompt_tokens if r.usage else 0,
            output_tokens=r.usage.completion_tokens if r.usage else 0,
            finish_reason=choice.finish_reason or "unknown",
            response_model=r.model or "",
            response_id=r.id or "",
            upstream=str(extra.get("provider", "")),
            quota=quota_from(raw.headers),
        )

    async def embed(self, model: str, texts: list[str]) -> tuple[list[list[float]], int]:
        """Search vectors (memory items), in input order, and the tokens used."""
        try:
            r = await self._client.embeddings.create(model=model, input=texts)
        except openai.APIError as e:
            raise self._error(e, tuple(texts)) from None
        vectors = [d.embedding for d in sorted(r.data, key=lambda d: d.index)]
        return vectors, r.usage.prompt_tokens if r.usage else 0

    def _error(self, e: openai.APIError, prompts: tuple[str, ...]) -> ProviderError:
        """Turn a provider error into a clear failure."""
        if isinstance(e, openai.APITimeoutError):
            return ProviderError("timeout", details=ErrorDetails(message="timed out"))
        if isinstance(e, openai.APIStatusError):
            details = self._details(e, prompts)
            kind = "rate_limited" if e.status_code == 429 else "provider_error"
            return ProviderError(kind, _reason(e.status_code, details.limit_source), details)
        return ProviderError(
            "provider_error", details=ErrorDetails(message=scrub(str(e), key=self._key))
        )

    def _details(self, e: openai.APIStatusError, prompts: tuple[str, ...]) -> ErrorDetails:
        """Keep everything the provider said, scrubbed."""
        body: dict[str, Any] = e.body if isinstance(e.body, dict) else {}
        found = body.get("metadata")
        meta: dict[str, Any] = found if isinstance(found, dict) else {}
        raw = str(meta.get("raw") or body.get("message") or e.message or "")

        def clean(value: object) -> str:
            """Remove keys and prompts from a value."""
            return scrub(str(value), key=self._key, prompts=prompts)

        return ErrorDetails(
            message=clean(raw),
            http_status=e.status_code,
            error_code=clean(body.get("code", meta.get("provider_error_code", ""))),
            upstream=clean(meta.get("provider_name", "")),
            limit_source=clean(meta.get("limit_source", "")),
            quota=quota_from(e.response.headers),
            retry_after=_seconds(e.response.headers.get("retry-after")),
        )


EMBED_MODELS = {
    "openai": "text-embedding-3-small",
    "gemini": "gemini-embedding-001",
    "openrouter": "openai/text-embedding-3-small",
}

USER_BASE_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "anthropic": "https://api.anthropic.com/v1/",
}


def same_model(requested: str, answered: str) -> bool:
    """Whether the reported model is the one asked for."""
    base = requested.split(":", 1)[0]
    return answered in (requested, base) or answered.startswith(base + "-20")
