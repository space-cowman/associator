"""Checks every uploaded file before it can be attached to a post."""

import io
import re
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

MB = 1024 * 1024
MAX_VIDEO_SECONDS = 60
MAX_PIXELS = 40_000_000


@dataclass(frozen=True)
class FileType:
    kind: str
    max_bytes: int
    inline: bool


TYPES: dict[str, FileType] = {
    "image/png": FileType("image", 5 * MB, True),
    "image/jpeg": FileType("image", 5 * MB, True),
    "image/webp": FileType("image", 5 * MB, True),
    "image/gif": FileType("image", 5 * MB, True),
    "application/pdf": FileType("pdf", 5 * MB, False),
    "text/plain": FileType("text", 1 * MB, False),
    "video/mp4": FileType("video", 25 * MB, True),
    "video/webm": FileType("video", 25 * MB, True),
}


class Rejected(Exception):
    """The file is not what it claims to be, or breaks a rule."""


def _matches(data: bytes, content_type: str) -> bool:
    """Check that the file's bytes match its claimed type."""
    head = data[:16]
    return {
        "image/png": head.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": head.startswith(b"\xff\xd8\xff"),
        "image/gif": head.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": head[:4] == b"RIFF" and head[8:12] == b"WEBP",
        "application/pdf": head.startswith(b"%PDF-"),
        "video/mp4": head[4:8] == b"ftyp",
        "video/webm": head.startswith(b"\x1a\x45\xdf\xa3"),
        "text/plain": b"\x00" not in data,
    }.get(content_type, False)


def _strip_image(data: bytes, content_type: str) -> bytes:
    """Redraw a photo without its location and camera data."""
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            out = io.BytesIO()
            if content_type == "image/gif":
                img.save(out, format="GIF", save_all=True, loop=img.info.get("loop", 0))
            else:
                upright = ImageOps.exif_transpose(img)
                fmt = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}[content_type]
                if fmt == "JPEG" and upright.mode not in ("RGB", "L"):
                    upright = upright.convert("RGB")
                upright.save(out, format=fmt, quality=90)
            return out.getvalue()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError):
        raise Rejected("The image could not be read or is too large") from None


def mp4_seconds(data: bytes) -> float | None:
    """Duration from the MP4 'mvhd' header, or None if it cannot be found."""
    i = data.find(b"mvhd")
    if i < 0 or len(data) < i + 36:
        return None
    if data[i + 4] == 1:
        timescale = int.from_bytes(data[i + 24 : i + 28], "big")
        duration = int.from_bytes(data[i + 28 : i + 36], "big")
    else:
        timescale = int.from_bytes(data[i + 16 : i + 20], "big")
        duration = int.from_bytes(data[i + 20 : i + 24], "big")
    return duration / timescale if timescale else None


def check(data: bytes, content_type: str) -> bytes:
    """The bytes to store, or Rejected."""
    file_type = TYPES.get(content_type)
    if file_type is None:
        raise Rejected("This file type is not allowed")
    if not data or len(data) > file_type.max_bytes:
        raise Rejected(f"Files of this type can be at most {file_type.max_bytes // MB} MB")
    if not _matches(data, content_type):
        raise Rejected("The file's contents do not match its type")
    if file_type.kind == "image":
        return _strip_image(data, content_type)
    if content_type == "video/mp4":
        seconds = mp4_seconds(data)
        if seconds is None or seconds > MAX_VIDEO_SECONDS:
            raise Rejected(f"Videos can be at most {MAX_VIDEO_SECONDS} seconds")
    if content_type == "text/plain":
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise Rejected("Text files must be plain UTF-8 text") from None
    return data


def safe_filename(name: str) -> str:
    """Only letters, digits, spaces and ."""
    cleaned = re.sub(r"[^A-Za-z0-9 ._()-]+", "_", name.strip()).strip(" ._") or "file"
    return cleaned[-120:]
