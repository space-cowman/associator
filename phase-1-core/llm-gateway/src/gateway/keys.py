"""Decrypts a user's saved model key for one call."""

import base64
import binascii
import uuid
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]
from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool

PURPOSE = "user-model-key"


async def decrypt(
    client: Any, key_arn: str, ciphertext_b64: str, user_id: uuid.UUID, model_id: uuid.UUID
) -> str:
    """Decrypt a person's saved model key with KMS."""
    try:
        blob = base64.b64decode(ciphertext_b64, validate=True)
        response = await run_in_threadpool(
            client.decrypt,
            CiphertextBlob=blob,
            KeyId=key_arn,
            EncryptionContext={
                "purpose": PURPOSE,
                "user_id": str(user_id),
                "model_id": str(model_id),
            },
        )
        return bytes(response["Plaintext"]).decode()
    except (binascii.Error, ValueError, ClientError, BotoCoreError):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "key_unavailable") from None
