"""Calls the safety service before anything is published."""

from typing import Any, Literal

import httpx
from fastapi import HTTPException, Request, status

from api import metrics

PERSONAL = {
    "EMAIL_ADDRESS": "email address",
    "PHONE_NUMBER": "phone number",
    "CREDIT_CARD": "card number",
    "IBAN_CODE": "bank account number",
    "US_SSN": "social security number",
    "IN_PAN": "PAN",
    "IN_AADHAAR": "Aadhaar number",
}


async def check(
    request: Request,
    text: str,
    sub_blocks: list[dict[str, Any]],
    *,
    personal_data: Literal["ask", "allow"] = "ask",
) -> list[dict[str, Any]]:
    """Return the warnings when the content may be published; raise 422 when it is blocked."""
    client: httpx.AsyncClient = request.app.state.safety
    try:
        response = await client.post("/check", json={"text": text, "sub_blocks": sub_blocks})
        response.raise_for_status()
        report = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Safety check unavailable, try again shortly"
        ) from None
    if not report["ok"]:
        hard = [b for b in report["blocks"] if b["check"] != "pii"]
        for b in report["blocks"]:
            action = (
                "blocked"
                if b["check"] != "pii"
                else "asked"
                if personal_data == "ask"
                else "allowed"
            )
            metrics.safety_finding(b["check"], b["kind"], action)
        if hard:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                {"message": "Remove the flagged content and try again", "blocks": hard},
            )
        if personal_data == "ask":
            kinds = sorted({PERSONAL.get(b["kind"], "personal data") for b in report["blocks"]})
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                {
                    "reason": "confirm_personal_data",
                    "message": f"This will be public and contains: {', '.join(kinds)}.",
                    "kinds": kinds,
                },
            )
    for w in report["warnings"]:
        metrics.safety_finding(w["check"], w["kind"], "warned")
    return list(report["warnings"])


CHUNK = 10_000
OVERLAP = 200


async def check_file_text(request: Request, content: str) -> None:
    """Scan a text attachment for leaked keys, 10 chunks per request."""
    starts = range(0, max(len(content), 1), CHUNK - OVERLAP)
    chunks = [content[i : i + CHUNK] for i in starts]
    client: httpx.AsyncClient = request.app.state.safety
    for i in range(0, len(chunks), 10):
        blocks = [{"kind": "logs", "content": c} for c in chunks[i : i + 10]]
        try:
            response = await client.post(
                "/check", json={"text": "", "sub_blocks": blocks, "secrets_only": True}
            )
            response.raise_for_status()
            report = response.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Safety check unavailable, try again shortly"
            ) from None
        if not report["ok"]:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                {
                    "message": "The file contains a key, token or password; remove it and retry",
                    "blocks": report["blocks"],
                },
            )
