"""Stands in for S3: stores objects in memory and records signed forms and links."""

import io
from typing import Any


class FakeS3:
    def __init__(self) -> None:
        """Start with an empty bucket."""
        self.objects: dict[str, bytes] = {}
        self.forms: list[dict[str, Any]] = []

    def generate_presigned_post(
        self, Bucket: str, Key: str, Fields: dict[str, str], Conditions: list[Any], ExpiresIn: int
    ) -> dict[str, Any]:  # noqa: N803
        """A fake signed upload form."""
        self.forms.append({"key": Key, "conditions": Conditions, "expires": ExpiresIn})
        return {
            "url": f"https://{Bucket}.s3.test/",
            "fields": {**Fields, "key": Key, "policy": "x"},
        }

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        """Read a stored object."""
        if Key not in self.objects:
            raise KeyError(Key)
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, Bucket: str, Key: str, Body: bytes, **_: Any) -> None:  # noqa: N803
        """Store an object."""
        self.objects[Key] = Body

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        """Read an object's details."""
        if Key not in self.objects:
            raise KeyError(Key)
        return {"ContentLength": len(self.objects[Key])}

    def copy_object(self, Bucket: str, Key: str, CopySource: dict[str, str], **_: Any) -> None:  # noqa: N803
        """Copy an object."""
        self.objects[Key] = self.objects[CopySource["Key"]]

    def delete_object(self, Bucket: str, Key: str) -> None:  # noqa: N803
        """Delete an object."""
        self.objects.pop(Key, None)

    def generate_presigned_url(self, op: str, Params: dict[str, Any], ExpiresIn: int) -> str:  # noqa: N803
        """A fake signed download link."""
        return f"https://{Params['Bucket']}.s3.test/{Params['Key']}?signed&expires={ExpiresIn}"
