import pytest
from fastapi.testclient import TestClient

from safety.main import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    """A test safety app."""
    with TestClient(create_app()) as c:
        yield c


def pii(client: TestClient, text: str = "", block: dict[str, object] | None = None) -> dict:
    """Check a text for personal data."""
    body = {"text": text, "sub_blocks": [block] if block else []}
    response = client.post("/check", json=body)
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize(
    ("text", "entity"),
    [
        ("mail me at ravi.test@example.com", "EMAIL_ADDRESS"),
        ("call +91 98765 43210 after 6", "PHONE_NUMBER"),
        ("or (415) 555-0132", "PHONE_NUMBER"),
        ("card 4111 1111 1111 1111", "CREDIT_CARD"),
        ("my PAN is ABCDE1234F", "IN_PAN"),
        ("aadhaar 2345 6789 0124", "IN_AADHAAR"),
    ],
)
def test_contact_and_id_numbers_block(client: TestClient, text: str, entity: str) -> None:
    """Contact and id numbers block."""
    result = pii(client, text)
    assert result["ok"] is False
    assert any(f["check"] == "pii" and f["kind"] == entity for f in result["blocks"])


def test_names_places_ips_only_warn(client: TestClient) -> None:
    """Names places ips only warn."""
    result = pii(client, "John Smith from Mumbai says 10.0.0.5 refused")
    assert result["ok"] is True
    assert {f["kind"] for f in result["warnings"]} == {"PERSON", "LOCATION", "IP_ADDRESS"}


def test_numbers_in_logs_do_not_block(client: TestClient) -> None:
    """Numbers in logs do not block."""
    logs = (
        "2026-10-26T12:00:01Z INFO request id=42 status=200\n"
        "port 5432 pid 98765 exit 137\nretry in 1234567890 ms\nversion 1.33.13"
    )
    result = pii(client, block={"kind": "logs", "content": logs})
    assert result["ok"] is True


def test_tech_question_is_clean(client: TestClient) -> None:
    """Tech question is clean."""
    result = pii(client, "Postgres or MySQL for a side project? My pod restarts on k3s.")
    assert result == {"ok": True, "over_limit": False, "blocks": [], "warnings": []}


def test_report_never_contains_the_value(client: TestClient) -> None:
    """Report never contains the value."""
    assert "ravi.test@example.com" not in str(pii(client, "mail ravi.test@example.com"))
