"""A stand-in for AWS KMS that checks the encryption context."""

import os
from typing import Any

from botocore.exceptions import ClientError  # type: ignore[import-untyped]


class FakeKms:
    def __init__(self) -> None:
        """Start with no keys."""
        self._store: dict[bytes, tuple[bytes, dict[str, str]]] = {}

    def encrypt(self, KeyId: str, Plaintext: bytes, EncryptionContext: dict[str, str]) -> Any:  # noqa: N803
        """Pretend to encrypt, keeping the context."""
        blob = os.urandom(48)
        self._store[blob] = (Plaintext, dict(EncryptionContext))
        return {"CiphertextBlob": blob}

    def decrypt(self, CiphertextBlob: bytes, KeyId: str, EncryptionContext: dict[str, str]) -> Any:  # noqa: N803
        """Decrypt, refusing a wrong context."""
        found = self._store.get(CiphertextBlob)
        if found is None or found[1] != EncryptionContext:
            raise ClientError({"Error": {"Code": "InvalidCiphertextException"}}, "Decrypt")
        return {"Plaintext": found[0]}
