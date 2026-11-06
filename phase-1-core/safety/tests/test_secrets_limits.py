import pytest
from fastapi.testclient import TestClient

from safety.main import create_app

client = TestClient(create_app())

SECRETS = {
    "AWS Access Key": "aws_access_key_id = AKIAIOSFODNN7EXAMPLE",  # pragma: allowlist secret
    "GitHub Token": "token ghp_" + "a1B2c3D4e5" * 3 + "a1B2c3",  # pragma: allowlist secret
    "Private Key": "-----BEGIN RSA " + "PRIVATE KEY-----",
    "OpenAI key": "OPENAI=sk-proj-" + "A1b2C3d4" * 6,
    "Anthropic key": "key sk-ant-api03-" + "Zz9Yy8Xx7W" * 3,
    "Google API key": "AIza" + "B" * 35,
    "Secret assignment": "export DB_PASSWORD=s3cr3tPass99",  # pragma: allowlist secret
}


def check(text: str = "", sub_blocks: list[dict[str, object]] | None = None) -> dict[str, object]:
    """Check a text through the app."""
    response = client.post("/check", json={"text": text, "sub_blocks": sub_blocks or []})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("kind", SECRETS)
def test_secret_in_logs_blocks_and_value_never_echoed(kind: str) -> None:
    """Secret in logs blocks and value never echoed."""
    line = SECRETS[kind]
    result = check(sub_blocks=[{"kind": "logs", "content": f"starting app\n{line}\ndone"}])
    assert result["ok"] is False
    assert any(f["check"] == "secret" for f in result["blocks"])  # type: ignore[union-attr]
    value = line.split()[-1].split("=")[-1]
    assert value not in str(result)


@pytest.mark.parametrize(
    "harmless",
    [
        "id 550e8400-e29b-41d4-a716-446655440000",
        "commit 3f2a9c1d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f",
        "image sha256:d071c94ab8f15af3cd0622d4900b77b5450b852751b408b557d453c5046cee09",
        'password = "${DB_PASSWORD}"',
        "API_KEY=$OPENAI_API_KEY",
        "I forgot my password yesterday",
    ],
)
def test_ordinary_log_lines_pass(harmless: str) -> None:
    """Ordinary log lines pass."""
    assert check(sub_blocks=[{"kind": "logs", "content": harmless}])["ok"] is True


def test_position_points_at_the_secret() -> None:
    """Position points at the secret."""
    text = "my key is AKIAIOSFODNN7EXAMPLE ok"  # pragma: allowlist secret
    finding = check(text)["blocks"][0]  # type: ignore[index]
    assert (
        text[finding["start"] : finding["end"]] == "AKIAIOSFODNN7EXAMPLE"
    )  # pragma: allowlist secret


def test_product_limits_are_findings_not_errors() -> None:
    """Product limits are findings not errors."""
    result = check(
        "x" * 501,
        [{"kind": "code", "content": "y" * 2001}, {"kind": "steps", "steps": ["s"] * 11}],
    )
    assert result["ok"] is False and result["over_limit"] is True
    assert {f["location"] for f in result["blocks"]} == {"text", "sub_blocks[0]", "sub_blocks[1]"}  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "body",
    [
        {"text": "x" * 5001},
        {"sub_blocks": [{"kind": "code", "steps": ["a"]}]},
        {"sub_blocks": [{"kind": "steps", "content": "a"}]},
        {"sub_blocks": [{"kind": "video", "content": "a"}]},
        {"sub_blocks": [{"kind": "logs", "content": "a"}] * 11},
        {"text": "a", "extra": 1},
    ],
)
def test_bad_requests_are_422(body: dict[str, object]) -> None:
    """Bad requests are 422."""
    assert client.post("/check", json=body).status_code == 422


def test_clean_post_is_ok() -> None:
    """Clean post is ok."""
    result = check("How do I restart a pod?", [{"kind": "steps", "steps": ["kubectl get pods"]}])
    assert result == {"ok": True, "over_limit": False, "blocks": [], "warnings": []}
