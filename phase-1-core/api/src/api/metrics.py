"""Business counters (OpenTelemetry), shown on the Grafana dashboards."""

from opentelemetry import metrics

_meter = metrics.get_meter("associator.api")

_drafts = _meter.create_counter(
    "associator.drafts.decided", description="AI drafts approved, edited or discarded"
)
_ai_calls = _meter.create_counter("associator.ai.calls", description="Model calls")
_ai_tokens = _meter.create_counter("associator.ai.tokens", description="Model tokens")
_ai_cost = _meter.create_counter("associator.ai.cost_usd", description="Model cost in US dollars")
_safety = _meter.create_counter(
    "associator.safety.findings", description="Safety findings on content people publish"
)
_chat = _meter.create_counter("associator.chat.events", description="Private-chat activity")
_reports = _meter.create_counter(
    "associator.reports", description="Reports received (each must be acknowledged within 24 h)"
)
_sockets = _meter.create_up_down_counter(
    "associator.chat.sockets", description="Open live connections (WebSockets)"
)


def draft_path(run_id: object, plan: object) -> str:
    """Count a draft decision by how the draft was made."""
    if run_id is None:
        return "direct"
    return "split" if isinstance(plan, list) and len(plan) >= 2 else "single"


def draft_decided(mode: str, outcome: str, path: str = "direct") -> None:
    """mode: ask_my_ai / platform_ai / mcp; outcome: approved / edited / discarded."""
    _drafts.add(1, {"mode": mode, "outcome": outcome, "path": path})


def ai_call(
    *,
    own_model: bool,
    privacy: str,
    model: str,
    ok: bool,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
) -> None:
    """Count one AI call."""
    labels = {"source": "own" if own_model else "platform", "privacy": privacy, "model": model[:60]}
    _ai_calls.add(1, {**labels, "outcome": "ok" if ok else "failed"})
    if ok:
        _ai_tokens.add(tokens_in, {**labels, "direction": "in"})
        _ai_tokens.add(tokens_out, {**labels, "direction": "out"})
        _ai_cost.add(cost_usd, labels)


def safety_finding(check: str, kind: str, action: str) -> None:
    """action: blocked (keys, limits), asked (personal data, waiting for confirmation), warned."""
    _safety.add(1, {"check": check, "kind": kind, "action": action})


def chat_event(event: str) -> None:
    """event: conversation, message, file, ai_answer, report."""
    _chat.add(1, {"event": event})


def socket_opened() -> None:
    """Count a chat socket opening."""
    _sockets.add(1)


def socket_closed() -> None:
    """Count a chat socket closing."""
    _sockets.add(-1)


def report_received(where: str) -> None:
    """where: question / reply / private_chat."""
    _reports.add(1, {"where": where})
