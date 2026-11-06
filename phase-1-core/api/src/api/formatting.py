"""Short formatted text for posts: bold, italic, code, lists and links."""

import re

_FENCED = re.compile(r"```[^\n`]*\n?(.*?)```", re.S)
_INLINE = re.compile(r"`([^`\n]+)`")


def code_spans(text: str) -> list[str]:
    """Every fenced block and inline code span in the text."""
    fenced = [m.group(1).strip() for m in _FENCED.finditer(text)]
    rest = _FENCED.sub(" ", text)
    inline = [m.group(1).strip() for m in _INLINE.finditer(rest)]
    return [c for c in fenced + inline if c]


def for_safety(text: str) -> list[dict[str, str]]:
    """Code spans as the safety service's code blocks."""
    return [{"kind": "code", "content": c[:10_000]} for c in code_spans(text)]


def warning_labels(warnings: list[dict[str, object]]) -> list[str]:
    """The labels to show on a post, each once."""
    labels: list[str] = []
    for w in warnings:
        kind = str(w.get("kind", ""))
        if w.get("check") in ("dangerous_command", "package") and kind not in labels:
            labels.append(kind)
    return labels
