"""Dangerous-command rules for code and steps."""

import re

RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "recursive delete of root, home or everything",
        re.compile(
            r"\brm\s+-[a-zA-Z]*(?:r[a-zA-Z]*f|f[a-zA-Z]*r)[a-zA-Z]*\s+(?:--\s+)?(?:/|~|\*|/\*|\$HOME)(?=\s|$|;|&)"
        ),
    ),
    (
        "download piped into a shell",
        re.compile(r"\b(?:curl|wget)\b[^|\n]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b"),
    ),
    (
        "PowerShell download and run",
        re.compile(
            r"(?i)\b(?:iex|invoke-expression)\b.*\b(?:iwr|invoke-webrequest|downloadstring)\b"
            r"|\b(?:iwr|invoke-webrequest)\b.*\|\s*(?:iex|invoke-expression)\b"
        ),
    ),
    ("world-writable permissions", re.compile(r"\bchmod\s+(?:-R\s+)?0?777\b")),
    ("fork bomb", re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:")),
    ("raw write to a disk", re.compile(r"\bdd\b[^\n]*\bof=/dev/(?:sd|nvme|xvd|hd|disk)")),
    ("format a disk", re.compile(r"\bmkfs(?:\.\w+)?\s+(?:-\S+\s+)*/dev/")),
    ("overwrite a disk device", re.compile(r">\s*/dev/(?:sd|nvme|xvd|hd)[a-z]")),
    ("drop a database, schema or table", re.compile(r"(?i)\bdrop\s+(?:database|schema|table)\b")),
    (
        "delete all Kubernetes resources or a namespace",
        re.compile(r"\bkubectl\s+delete\b[^\n]*(?:--all\b|\bnamespaces?\b|\bns\b)"),
    ),
    (
        "destroy infrastructure without confirmation",
        re.compile(r"\bterraform\s+destroy\b[^\n]*-auto-approve"),
    ),
    ("force-push", re.compile(r"\bgit\s+push\b[^\n]*(?:--force\b|\s-f\b)")),
    (
        "disable TLS certificate checks",
        re.compile(
            r"\b(?:curl\b[^\n]*\s(?:-k|--insecure)\b|verify\s*=\s*False\b|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['\"]?0)"
        ),
    ),
)


def find_dangerous(text: str) -> list[tuple[str, int, int]]:
    """(label, start, end) for each risky command found."""
    return [(label, m.start(), m.end()) for label, rule in RULES for m in rule.finditer(text)]
