import base64
import binascii
import json
import mimetypes
import struct
from pathlib import Path
from typing import Any, Dict, Optional


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json_file(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def parse_input_image(value: Optional[str]) -> Optional[Dict[str, str]]:
    if not value:
        return None
    if is_url(value):
        return {"kind": "url", "value": value}
    if value.startswith("data:image/"):
        return {"kind": "data_uri", "value": value}

    path = Path(value)
    if path.exists() and path.is_file():
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return {"kind": "data_uri", "value": f"data:{mime};base64,{b64}"}

    # Treat unknown inputs as raw base64 for flexibility.
    return {"kind": "base64", "value": value}


def infer_image_size(value: Optional[str]) -> Optional[str]:
    payload = _load_image_bytes(value)
    if not payload:
        return None
    dimensions = _extract_dimensions(payload)
    if not dimensions:
        return None
    width, height = dimensions
    return f"{width}x{height}"


def _load_image_bytes(value: Optional[str]) -> Optional[bytes]:
    if not value:
        return None

    if value.startswith("data:image/"):
        if "," not in value:
            return None
        _, data = value.split(",", 1)
        return _safe_b64decode(data)

    path = Path(value)
    if path.exists() and path.is_file():
        return path.read_bytes()

    # Try raw base64 input.
    return _safe_b64decode(value)


def _safe_b64decode(value: str) -> Optional[bytes]:
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        return None


def _extract_dimensions(data: bytes) -> Optional[tuple[int, int]]:
    for parser in (_png_dimensions, _jpeg_dimensions, _gif_dimensions, _bmp_dimensions):
        result = parser(data)
        if result:
            return result
    return None


def _png_dimensions(data: bytes) -> Optional[tuple[int, int]]:
    if len(data) < 24:
        return None
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _jpeg_dimensions(data: bytes) -> Optional[tuple[int, int]]:
    if len(data) < 4 or data[0:2] != b"\xFF\xD8":
        return None
    i = 2
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            return None
        marker = data[i]
        i += 1
        if marker in {0xD8, 0xD9}:
            continue
        if marker == 0xDA:
            return None
        if i + 2 > len(data):
            return None
        segment_length = struct.unpack(">H", data[i : i + 2])[0]
        if segment_length < 2 or i + segment_length > len(data):
            return None
        if marker in sof_markers:
            if i + 7 > len(data):
                return None
            height, width = struct.unpack(">HH", data[i + 3 : i + 7])
            return width, height
        i += segment_length
    return None


def _gif_dimensions(data: bytes) -> Optional[tuple[int, int]]:
    if len(data) < 10:
        return None
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    width, height = struct.unpack("<HH", data[6:10])
    return width, height


def _bmp_dimensions(data: bytes) -> Optional[tuple[int, int]]:
    if len(data) < 26 or data[:2] != b"BM":
        return None
    width = int.from_bytes(data[18:22], "little", signed=True)
    height = int.from_bytes(data[22:26], "little", signed=True)
    if width <= 0 or height == 0:
        return None
    return width, abs(height)


def json_dump(path: Path, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
