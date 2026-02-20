import base64
from pathlib import Path

from cli import _resolve_request_size
from core.io_utils import infer_image_size

# 1x1 PNG
PNG_1X1_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7ZqZ0AAAAASUVORK5CYII="
)


def test_infer_image_size_from_data_uri() -> None:
    value = f"data:image/png;base64,{PNG_1X1_BASE64}"
    assert infer_image_size(value) == "1x1"


def test_infer_image_size_from_file(tmp_path: Path) -> None:
    data = base64.b64decode(PNG_1X1_BASE64)
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(data)
    assert infer_image_size(str(image_path)) == "1x1"


def test_resolve_size_text_to_image_defaults_to_1024() -> None:
    assert _resolve_request_size("text_to_image", None, None) == "1024x1024"


def test_resolve_size_image_to_image_uses_source_size() -> None:
    value = f"data:image/png;base64,{PNG_1X1_BASE64}"
    assert _resolve_request_size("image_to_image", None, value) == "1x1"
