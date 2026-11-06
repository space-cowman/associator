import io
import struct

import pytest
from PIL import Image

from api import files


def jpeg_with_gps() -> bytes:
    """A photo that carries a location."""
    img = Image.new("RGB", (40, 30), "orange")
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"
    exif[0x8825] = {1: "N", 2: (19.0, 4.0, 30.0)}
    out = io.BytesIO()
    img.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def mp4(seconds: int) -> bytes:
    """A short test video."""
    ftyp = struct.pack(">I4s4sI", 16, b"ftyp", b"isom", 0)
    mvhd_body = bytes([0, 0, 0, 0]) + struct.pack(">IIII", 0, 0, 1000, seconds * 1000) + b"\0" * 80
    mvhd = struct.pack(">I4s", 8 + len(mvhd_body), b"mvhd") + mvhd_body
    moov = struct.pack(">I4s", 8 + len(mvhd), b"moov") + mvhd
    return ftyp + moov


def test_photo_location_and_camera_data_are_removed() -> None:
    """Photo location and camera data are removed."""
    original = jpeg_with_gps()
    assert Image.open(io.BytesIO(original)).getexif()
    cleaned = files.check(original, "image/jpeg")
    assert not Image.open(io.BytesIO(cleaned)).getexif()


@pytest.mark.parametrize(
    ("data", "content_type"),
    [
        (b"#!/bin/sh\nrm -rf /", "image/png"),
        (b"MZ\x90\x00 windows exe", "application/pdf"),
        (b"%PDF-1.7", "video/mp4"),
        (b"text with a \x00 byte", "text/plain"),
        (b"\xff\xfe not utf8 \xc3\x28", "text/plain"),
        (b"\x89PNG\r\n\x1a\n" + b"garbage", "image/png"),
    ],
)
def test_contents_must_match_the_type(data: bytes, content_type: str) -> None:
    """Contents must match the type."""
    with pytest.raises(files.Rejected):
        files.check(data, content_type)


def test_types_and_sizes() -> None:
    """Types and sizes."""
    with pytest.raises(files.Rejected, match="not allowed"):
        files.check(b"<svg/>", "image/svg+xml")
    with pytest.raises(files.Rejected, match="at most 1 MB"):
        files.check(b"a" * (files.MB + 1), "text/plain")


def test_video_length_limit() -> None:
    """Video length limit."""
    assert files.mp4_seconds(mp4(42)) == 42
    assert files.check(mp4(60), "video/mp4")
    with pytest.raises(files.Rejected, match="60 seconds"):
        files.check(mp4(61), "video/mp4")


def test_decompression_bomb_is_refused() -> None:
    """Decompression bomb is refused."""
    big = io.BytesIO()
    Image.new("1", (9000, 9000)).save(big, format="PNG")
    with pytest.raises(files.Rejected):
        files.check(big.getvalue(), "image/png")


@pytest.mark.parametrize(
    ("name", "safe"),
    [
        ("my photo.png", "my photo.png"),
        ("../../etc/passwd", "etc_passwd"),
        ('a"b;c.pdf', "a_b_c.pdf"),
        ("", "file"),
    ],
)
def test_filenames_are_cleaned(name: str, safe: str) -> None:
    """Filenames are cleaned."""
    assert files.safe_filename(name) == safe
