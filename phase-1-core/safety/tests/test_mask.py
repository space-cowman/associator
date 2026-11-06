"""Masking for private content: personal data -> placeholders, secrets removed for good."""

import pytest
from fastapi.testclient import TestClient

from safety.main import create_app

AWS_KEY = "AKIAIOSFODNN7EXAMPLE"  # pragma: allowlist secret


@pytest.fixture(scope="module")
def client() -> TestClient:
    """A test safety app."""
    with TestClient(create_app()) as c:
        yield c


def mask(client: TestClient, *texts: str, names: list[str] | None = None) -> dict:
    """Mask texts through the app."""
    r = client.post("/mask", json={"texts": list(texts), "names": names or []})
    assert r.status_code == 200, r.text
    return r.json()


def restore(text: str, table: dict[str, str]) -> str:
    """Put the original values back."""
    for token, value in table.items():
        text = text.replace(token, value)
    return text


@pytest.mark.parametrize(
    ("text", "value", "label"),
    [
        ("mail me at ravi.m@example.com today", "ravi.m@example.com", "EMAIL"),
        ("call +91 98765 43210 after 6", "+91 98765 43210", "PHONE"),
        ("aadhaar 2345 6789 0124 is mine", "2345 6789 0124", "AADHAAR"),
        ("my PAN is ABCPE1234F", "ABCPE1234F", "PAN"),
        ("the server is at 203.0.113.42", "203.0.113.42", "IP"),
    ],
)
def test_personal_data_becomes_a_placeholder(
    client: TestClient, text: str, value: str, label: str
) -> None:
    """Personal data becomes a placeholder."""
    out = mask(client, text)
    assert value not in out["texts"][0]
    assert f"<{label}_1>" in out["texts"][0]
    assert out["table"][f"<{label}_1>"] == value


def test_names_and_places(client: TestClient) -> None:
    """Names and places."""
    out = mask(client, "Priya Sharma moved to Ahmedabad last year")
    masked = out["texts"][0]
    assert "Priya Sharma" not in masked and "Ahmedabad" not in masked
    assert "<PERSON_1>" in masked and "<PLACE_1>" in masked


def test_same_value_same_placeholder_across_texts(client: TestClient) -> None:
    """Same value same placeholder across texts."""
    out = mask(client, "write to a@example.com", "cc a@example.com and b@example.com")
    assert out["texts"] == ["write to <EMAIL_1>", "cc <EMAIL_1> and <EMAIL_2>"]


def test_secrets_are_removed_and_never_come_back(client: TestClient) -> None:
    """Secrets are removed and never come back."""
    out = mask(client, f"key = {AWS_KEY}")
    assert AWS_KEY not in out["texts"][0] and "[SECRET REMOVED]" in out["texts"][0]
    assert AWS_KEY not in out["table"].values() and out["secrets_removed"] == 1


def test_member_handles(client: TestClient) -> None:
    """Member handles."""
    out = mask(client, "ask @Ravi or ravi about gravity", names=["ravi"])
    assert out["texts"][0] == "ask <USER_1> or <USER_1> about gravity"
    assert out["table"]["<USER_1>"] == "@ravi"


def test_typed_placeholders_are_neutralised(client: TestClient) -> None:
    """Typed placeholders are neutralised."""
    out = mask(client, "literally <EMAIL_1> and real b@example.com")
    assert out["texts"][0] == "literally [EMAIL_1] and real <EMAIL_1>"


def test_restoring_gives_the_original_back(client: TestClient) -> None:
    """Restoring gives the original back."""
    original = "Ping Priya Sharma at priya@example.com or +91 98765 43210"
    out = mask(client, original)
    assert restore(out["texts"][0], out["table"]) == original


@pytest.mark.parametrize(
    "body",
    [
        {"texts": ["x"] * 21},
        {"texts": ["x" * 20_001]},
        {"texts": ["hi"], "names": ["Bad Name!"]},
        {"texts": ["hi"], "extra": 1},
    ],
)
def test_size_and_shape_limits(client: TestClient, body: dict) -> None:
    """Size and shape limits."""
    assert client.post("/mask", json=body).status_code == 422


def test_personal_data_never_reaches_the_logs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Personal data never reaches the logs."""
    import logging

    with caplog.at_level(logging.DEBUG):
        mask(client, "mail priya@example.com")
        client.post("/check", json={"text": "mail priya@example.com"})
    assert "priya@example.com" not in caplog.text
