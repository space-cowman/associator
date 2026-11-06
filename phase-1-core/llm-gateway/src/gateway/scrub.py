"""Removes keys and prompts from provider messages before logging."""

import re

KEY_PATTERNS = re.compile(
    r"(?:\bsk-[A-Za-z0-9_*.-]{3,}[A-Za-z0-9_*]|\bgsk_[A-Za-z0-9_*]{4,}|\bAIza[0-9A-Za-z_*-]{4,}"
    r"|\bhf_[A-Za-z0-9*]{4,}|\bgh[pousr]_[A-Za-z0-9*]{4,}|\bgithub_pat_[A-Za-z0-9_*]{4,}"
    r"|\bBearer\s+[A-Za-z0-9._*-]{7,}[A-Za-z0-9_*])"
)
MAX_LENGTH = 1000
MIN_PROMPT = 8


def scrub(message: str, *, key: str = "", prompts: tuple[str, ...] = ()) -> str:
    """Remove keys and prompts from an error message."""
    text = message.replace(key, "<KEY>") if key else message
    text = KEY_PATTERNS.sub("<KEY>", text)
    for prompt in sorted(prompts, key=len, reverse=True):
        if len(prompt) >= MIN_PROMPT:
            text = text.replace(prompt, "<PROMPT>")
    return text[:MAX_LENGTH]
