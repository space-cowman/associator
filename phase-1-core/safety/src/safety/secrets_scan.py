"""Secret detection: Yelp detect-secrets' named detectors plus a few patterns of our own."""

import re
import threading

from detect_secrets.core import scan
from detect_secrets.core.plugins.util import get_mapping_from_secret_type_to_class
from detect_secrets.settings import transient_settings

_SKIP = {"Base64HighEntropyString", "HexHighEntropyString", "IPPublicDetector"}
_DETECTORS: list[type] = list(get_mapping_from_secret_type_to_class().values())
_PLUGINS = {"plugins_used": [{"name": d.__name__} for d in _DETECTORS if d.__name__ not in _SKIP]}
_LOCK = threading.Lock()

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("OpenAI key", re.compile(r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("OpenRouter key", re.compile(r"\bsk-or-v1-[A-Za-z0-9]{32,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{30,}")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}")),
    (
        "Secret assignment",
        re.compile(
            r"(?i)\b[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PASSWD|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY)"
            r"[A-Z0-9_]*\s*[=:]\s*['\"]?(?P<value>[^\s'\"$<{][^\s'\"]{7,})"
        ),
    ),
)


def find_secrets(text: str) -> list[tuple[str, int, int]]:
    """(kind, start, end) for each secret in text."""
    hits: list[tuple[str, int, int]] = []
    for kind, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            start, end = m.span("value") if "value" in pattern.groupindex else m.span()
            hits.append((kind, start, end))
    offset = 0
    with _LOCK, transient_settings(_PLUGINS):
        for line in text.splitlines(keepends=True):
            for secret in scan.scan_line(line):
                at = line.find(secret.secret_value or "")
                start, end = (
                    (at, at + len(secret.secret_value or "")) if at >= 0 else (0, len(line))
                )
                hits.append((secret.type, offset + start, offset + end))
            offset += len(line)
    return _dedupe(hits)


def _dedupe(hits: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
    """Keep one finding per place."""
    kept: list[tuple[str, int, int]] = []
    for kind, start, end in sorted(hits, key=lambda h: (h[1], -(h[2] - h[1]))):
        if not any(s <= start and end <= e for _, s, e in kept):
            kept.append((kind, start, end))
    return kept
