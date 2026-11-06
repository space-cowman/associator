"""Text rules shared by routes."""

import unicodedata

BIDI_CONTROLS = frozenset("‪‫‬‭‮⁦⁧⁨⁩")


def visible_text_only(value: str) -> str:
    """Names: no control or invisible format characters at all."""
    if any(unicodedata.category(ch) in ("Cc", "Cf") for ch in value):
        raise ValueError("contains invisible or control characters")
    return value


def safe_multiline(value: str) -> str:
    """Check post text for unsafe control characters."""
    for ch in value:
        if ch in BIDI_CONTROLS or (unicodedata.category(ch) == "Cc" and ch not in "\n\r\t"):
            raise ValueError("contains control or text-direction characters")
    return value
