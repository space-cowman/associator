"""Encrypts users' model API keys with AWS KMS."""

import uuid
from typing import Any

from fastapi.concurrency import run_in_threadpool

PURPOSE = "user-model-key"


def context(user_id: uuid.UUID, model_id: uuid.UUID) -> dict[str, str]:
    """The KMS encryption context for a saved model key."""
    return {"purpose": PURPOSE, "user_id": str(user_id), "model_id": str(model_id)}


async def encrypt(client: Any, key_arn: str, plaintext: str, ctx: dict[str, str]) -> bytes:
    """Encrypt text with KMS."""
    response = await run_in_threadpool(
        client.encrypt, KeyId=key_arn, Plaintext=plaintext.encode(), EncryptionContext=ctx
    )
    return bytes(response["CiphertextBlob"])
