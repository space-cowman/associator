"""One record and metrics per model call."""

import json
import logging
from collections.abc import Callable, Iterable

from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation

log = logging.getLogger("gateway.calls")

_duration = metrics.get_meter("associator.gateway").create_histogram(
    "associator.gateway.call.duration",
    unit="s",
    description="Model call duration",
    explicit_bucket_boundaries_advisory=[0.5, 1, 2, 3, 5, 8, 13, 20, 30, 60],
)

_quota: dict[tuple[str, str, str], int] = {}


def _observe(prefix: str) -> Callable[[CallbackOptions], Iterable[Observation]]:
    """Register a gauge for quota numbers."""

    def callback(options: CallbackOptions) -> Iterable[Observation]:
        """Report the stored quota numbers."""
        for (provider, model, name), value in list(_quota.items()):
            if name.endswith(prefix):
                unit = name.split("_", 1)[0]
                yield Observation(value, {"provider": provider, "model": model, "unit": unit})

    return callback


_meter = metrics.get_meter("associator.gateway")
_meter.create_observable_gauge(
    "associator.gateway.quota.remaining",
    callbacks=[_observe("_remaining")],
    description="Platform quota left (Groq: requests today, tokens this minute)",
)
_meter.create_observable_gauge(
    "associator.gateway.quota.limit",
    callbacks=[_observe("_limit")],
    description="Platform quota size (Groq: requests per day, tokens per minute)",
)


_fallbacks = _meter.create_counter(
    "associator.gateway.fallbacks", description="Platform calls answered by the backup model"
)


def fallback(from_model: str, to_model: str, kind: str) -> None:
    """Count a switch to the backup model."""
    _fallbacks.add(1, {"from_model": from_model, "to_model": to_model, "kind": kind})


def quota(provider: str, model: str, numbers: dict[str, int]) -> None:
    """Remember the provider's quota numbers."""
    for name, value in numbers.items():
        _quota[(provider, model, name)] = value


PRICES_PER_MTOK: dict[tuple[str, str], tuple[float, float]] = {
    ("groq", "openai/gpt-oss-120b"): (0.0, 0.0),
    ("fake", "fake-1"): (0.0, 0.0),
}


def cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """The cost of a call in US dollars."""
    price_in, price_out = PRICES_PER_MTOK.get((provider, model), (0.0, 0.0))
    return round((input_tokens * price_in + output_tokens * price_out) / 1_000_000, 6)


def record(
    *,
    request_id: str,
    user_id: str,
    provider: str,
    model: str,
    duration_ms: int,
    input_tokens: int = 0,
    output_tokens: int = 0,
    finish_reason: str = "",
    response_model: str = "",
    response_id: str = "",
    upstream: str = "",
    error: str = "",
    error_reason: str = "",
    error_message: str = "",
    provider_http_status: int = 0,
    provider_error_code: str = "",
    limit_source: str = "",
    kind: str = "user",
) -> None:
    """Log and count one model call."""
    _duration.record(
        duration_ms / 1000,
        {
            "model": model,
            "provider": provider,
            "kind": kind,
            "outcome": "error" if error else "ok",
            "reason": error_reason if error else "",
        },
    )
    log.info(
        json.dumps(
            {
                "request_id": request_id,
                "platform.user_id": user_id,
                "gen_ai.system": provider,
                "gen_ai.request.model": model,
                "gen_ai.response.model": response_model,
                "gen_ai.usage.input_tokens": input_tokens,
                "gen_ai.usage.output_tokens": output_tokens,
                "gen_ai.response.finish_reasons": [finish_reason] if finish_reason else [],
                "platform.cost_usd": cost_usd(provider, model, input_tokens, output_tokens),
                "gen_ai.response.id": response_id,
                "provider.upstream": upstream,
                "duration_ms": duration_ms,
                "error.type": error,
                "error.reason": error_reason,
                "error.message": error_message,
                "provider.http_status": provider_http_status,
                "provider.error_code": provider_error_code,
                "provider.limit_source": limit_source,
            }
        )
    )
