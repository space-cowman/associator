"""Masking for private content sent to an AI (privacy layer, step 2)."""

import re

from safety.pii import find_pii
from safety.secrets_scan import find_secrets

LABELS = {
    "PERSON": "PERSON",
    "LOCATION": "PLACE",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "CREDIT_CARD": "CARD",
    "IBAN_CODE": "IBAN",
    "US_SSN": "SSN",
    "IN_PAN": "PAN",
    "IN_AADHAAR": "AADHAAR",
    "IP_ADDRESS": "IP",
}
REMOVED = "[SECRET REMOVED]"
PLACEHOLDER = re.compile(r"<([A-Z]+_\d+)>")


class Masker:
    """One per request: the same value gets the same placeholder in every text."""

    def __init__(self) -> None:
        """Start with no placeholders."""
        self.table: dict[str, str] = {}
        self._by_value: dict[tuple[str, str], str] = {}
        self._counts: dict[str, int] = {}
        self.secrets_removed = 0

    def _placeholder(self, label: str, value: str, original: str) -> str:
        """The placeholder for a value, the same each time."""
        key = (label, value)
        if key not in self._by_value:
            self._counts[label] = self._counts.get(label, 0) + 1
            token = f"<{label}_{self._counts[label]}>"
            self._by_value[key] = token
            self.table[token] = original
        return self._by_value[key]

    def mask(self, text: str, names: list[str]) -> str:
        """Mask personal data and names in a text."""
        text = PLACEHOLDER.sub(r"[\1]", text)
        spans: list[tuple[int, int, str | None]] = []
        spans += [(s, e, None) for _kind, s, e in find_secrets(text)]
        spans += [(s, e, LABELS[k]) for k, _sev, s, e in find_pii(text, "text") if k in LABELS]
        for name in names:
            for m in re.finditer(rf"@?\b{re.escape(name)}\b", text, flags=re.IGNORECASE):
                spans.append((m.start(), m.end(), "USER"))
        spans.sort(key=lambda sp: (sp[2] is not None, -(sp[1] - sp[0]), sp[0]))
        chosen: list[tuple[int, int, str | None]] = []
        for sp in spans:
            if all(sp[1] <= c[0] or sp[0] >= c[1] for c in chosen):
                chosen.append(sp)
        out, pos = [], 0
        for start, end, label in sorted(chosen):
            out.append(text[pos:start])
            value = text[start:end]
            if label is None:
                out.append(REMOVED)
                self.secrets_removed += 1
            elif label == "USER":
                handle = value.lstrip("@").lower()
                out.append(self._placeholder("USER", handle, f"@{handle}"))
            else:
                out.append(self._placeholder(label, value, value))
            pos = end
        out.append(text[pos:])
        return "".join(out)
