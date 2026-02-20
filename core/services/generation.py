import base64
import binascii
import io
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import requests
from PIL import Image, UnidentifiedImageError

from adapters import AlibabaAdapter, GLMAdapter, GoogleAdapter
from core.io_utils import infer_image_size
from core.models import TASK_IMAGE2IMAGE, GenerationRequest

LOGGER = logging.getLogger("image_gen_test_tool")

ALIBABA_HOSTS = {
    "intl": "https://dashscope-intl.aliyuncs.com",
    "cn": "https://dashscope.aliyuncs.com",
}
ALIBABA_SYNC_PATH = "/api/v1/services/aigc/multimodal-generation/generation"
ALIBABA_ASYNC_PATH = "/api/v1/services/aigc/image-generation/generation"
GOOGLE_GENERATE_CONTENT_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
GLM_BASE_URL_DEFAULT = "https://open.bigmodel.cn/api/paas/v4"
GLM_IMAGE_GENERATIONS_PATH = "/images/generations"
ALIBABA_IMAGE_MIN = 512
ALIBABA_IMAGE_MAX = 2048
ALIBABA_AUTOCROP_ENV = "IGT_ALIBABA_IMAGE2IMAGE_AUTOCROP"


def build_adapters_from_env() -> Dict[str, object]:
    timeout = int(os.getenv("HTTP_TIMEOUT_SECONDS", "120"))
    alibaba_region = os.getenv("ALIBABA_REGION", "intl").strip().lower()
    alibaba_host = ALIBABA_HOSTS.get(alibaba_region, ALIBABA_HOSTS["intl"])
    alibaba_sync_url = os.getenv("ALIBABA_TEXT2IMAGE_URL", "").strip() or (
        f"{alibaba_host}{ALIBABA_SYNC_PATH}"
    )
    alibaba_image2image_url = os.getenv("ALIBABA_IMAGE2IMAGE_URL", "").strip() or alibaba_sync_url
    alibaba_async_url = os.getenv("ALIBABA_ASYNC_URL", "").strip() or (
        f"{alibaba_host}{ALIBABA_ASYNC_PATH}"
    )
    google_text2image_url = (
        os.getenv("GOOGLE_TEXT2IMAGE_URL", "").strip() or GOOGLE_GENERATE_CONTENT_URL
    )
    google_image2image_url = (
        os.getenv("GOOGLE_IMAGE2IMAGE_URL", "").strip() or GOOGLE_GENERATE_CONTENT_URL
    )
    glm_base_url = os.getenv("GLM_BASE_URL", "").strip() or GLM_BASE_URL_DEFAULT
    glm_text2image_url = (
        os.getenv("GLM_TEXT2IMAGE_URL", "").strip() or f"{glm_base_url}{GLM_IMAGE_GENERATIONS_PATH}"
    )
    glm_image2image_url = os.getenv("GLM_IMAGE2IMAGE_URL", "").strip() or glm_text2image_url

    return {
        "alibaba": AlibabaAdapter(
            api_key=os.getenv("ALIBABA_API_KEY", ""),
            text2image_url=alibaba_sync_url,
            image2image_url=alibaba_image2image_url,
            timeout_seconds=timeout,
            async_mode=os.getenv("ALIBABA_ASYNC", "false").strip().lower() == "true",
            async_url=alibaba_async_url,
            poll_interval_seconds=int(os.getenv("ALIBABA_POLL_INTERVAL_SECONDS", "10")),
            poll_timeout_seconds=int(os.getenv("ALIBABA_POLL_TIMEOUT_SECONDS", "300")),
        ),
        "google": GoogleAdapter(
            api_key=os.getenv("GOOGLE_API_KEY", ""),
            text2image_url=google_text2image_url,
            image2image_url=google_image2image_url,
            timeout_seconds=timeout,
        ),
        "glm": GLMAdapter(
            api_key=os.getenv("GLM_API_KEY", ""),
            text2image_url=glm_text2image_url,
            image2image_url=glm_image2image_url,
            timeout_seconds=timeout,
        ),
    }


def resolve_request_size(
    task_type: str, supplied_size: Optional[str], input_image: Optional[str]
) -> Optional[str]:
    if supplied_size:
        return supplied_size
    if task_type == TASK_IMAGE2IMAGE:
        inferred = infer_image_size(input_image)
        if inferred:
            LOGGER.info("size auto-detected from source image: %s", inferred)
            return inferred
        LOGGER.info("size not detected from source image; request will not include size.")
        return None
    return "1024x1024"


def prepare_request_for_execution(
    request: GenerationRequest,
) -> tuple[GenerationRequest, List[Path]]:
    if request.task_type != TASK_IMAGE2IMAGE or request.provider != "alibaba":
        return request, []
    if not request.input_image:
        return request, []
    if not is_alibaba_autocrop_enabled():
        LOGGER.info("auto-crop disabled by env: %s", ALIBABA_AUTOCROP_ENV)
        return request, []

    source_image = _load_source_image(request.input_image)
    if source_image is None:
        LOGGER.info("auto-crop skipped: failed to load source image.")
        return request, []

    source_width, source_height = source_image.size
    requested_size = _parse_size(request.size)
    target_width, target_height = _resolve_target_size(
        source_width=source_width,
        source_height=source_height,
        requested_size=requested_size,
    )
    target_size_text = f"{target_width}x{target_height}"

    prepared = request.model_copy(deep=True)
    prepared.size = target_size_text

    if source_width == target_width and source_height == target_height:
        if request.size != target_size_text:
            LOGGER.info(
                "auto-crop normalized request size only: source=%sx%s target=%s",
                source_width,
                source_height,
                target_size_text,
            )
        if not _persist_preprocessed_input_enabled():
            return prepared, []
        copied = source_image.copy()
        temp_copy = _write_temp_png(copied)
        prepared.input_image = str(temp_copy)
        LOGGER.info(
            "auto-crop persisted effective input copy: source=%sx%s temp=%s",
            source_width,
            source_height,
            temp_copy,
        )
        return prepared, [temp_copy]

    processed = _center_crop_and_resize(source_image, target_width, target_height)
    tmp_path = _write_temp_png(processed)
    prepared.input_image = str(tmp_path)
    LOGGER.info(
        "auto-crop applied: source=%sx%s target=%sx%s temp=%s",
        source_width,
        source_height,
        target_width,
        target_height,
        tmp_path,
    )
    return prepared, [tmp_path]


def _resolve_target_size(
    source_width: int,
    source_height: int,
    requested_size: Optional[tuple[int, int]],
) -> tuple[int, int]:
    if requested_size is None or requested_size == (source_width, source_height):
        return _fit_size_within_bounds(source_width, source_height)
    return _clamp_size(requested_size[0], requested_size[1])


def _fit_size_within_bounds(width: int, height: int) -> tuple[int, int]:
    w = float(width)
    h = float(height)

    if w <= 0 or h <= 0:
        return ALIBABA_IMAGE_MIN, ALIBABA_IMAGE_MIN

    if w > ALIBABA_IMAGE_MAX or h > ALIBABA_IMAGE_MAX:
        scale_down = min(ALIBABA_IMAGE_MAX / w, ALIBABA_IMAGE_MAX / h)
        w *= scale_down
        h *= scale_down

    if w < ALIBABA_IMAGE_MIN or h < ALIBABA_IMAGE_MIN:
        scale_up = max(ALIBABA_IMAGE_MIN / w, ALIBABA_IMAGE_MIN / h)
        w *= scale_up
        h *= scale_up

    return _clamp_size(int(round(w)), int(round(h)))


def _clamp_size(width: int, height: int) -> tuple[int, int]:
    return (
        max(ALIBABA_IMAGE_MIN, min(ALIBABA_IMAGE_MAX, width)),
        max(ALIBABA_IMAGE_MIN, min(ALIBABA_IMAGE_MAX, height)),
    )


def _parse_size(value: Optional[str]) -> Optional[tuple[int, int]]:
    if not value:
        return None
    text = value.strip().lower()
    if "x" not in text:
        return None
    left, right = text.split("x", 1)
    if not (left.isdigit() and right.isdigit()):
        return None
    width = int(left)
    height = int(right)
    if width <= 0 or height <= 0:
        return None
    return width, height


def _load_source_image(value: str) -> Optional[Image.Image]:
    try:
        image_bytes = _load_image_bytes(value)
    except Exception:  # noqa: BLE001
        return None
    if not image_bytes:
        return None
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.load()
            return image.copy()
    except (UnidentifiedImageError, OSError):
        return None


def _load_image_bytes(value: str) -> Optional[bytes]:
    if value.startswith("data:image/"):
        if "," not in value:
            return None
        _, payload = value.split(",", 1)
        return _safe_b64decode(payload)

    if value.startswith("http://") or value.startswith("https://"):
        timeout = int(os.getenv("HTTP_TIMEOUT_SECONDS", "120"))
        response = requests.get(value, timeout=timeout)
        response.raise_for_status()
        return response.content

    path = Path(value)
    if path.exists() and path.is_file():
        return path.read_bytes()

    return _safe_b64decode(value)


def _safe_b64decode(payload: str) -> Optional[bytes]:
    try:
        return base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error):
        return None


def _persist_preprocessed_input_enabled() -> bool:
    raw = os.getenv("IGT_PERSIST_PREPROCESSED_INPUT", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def is_alibaba_autocrop_enabled() -> bool:
    raw = os.getenv(ALIBABA_AUTOCROP_ENV, "off").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _center_crop_and_resize(
    image: Image.Image,
    target_width: int,
    target_height: int,
) -> Image.Image:
    source_width, source_height = image.size
    target_ratio = target_width / target_height
    source_ratio = source_width / source_height

    if source_ratio > target_ratio:
        crop_height = source_height
        crop_width = int(round(source_height * target_ratio))
    else:
        crop_width = source_width
        crop_height = int(round(source_width / target_ratio))

    crop_width = max(1, min(source_width, crop_width))
    crop_height = max(1, min(source_height, crop_height))
    left = max(0, (source_width - crop_width) // 2)
    top = max(0, (source_height - crop_height) // 2)
    cropped = image.crop((left, top, left + crop_width, top + crop_height))
    resampling = getattr(Image, "Resampling", Image)
    resized = cropped.resize((target_width, target_height), resampling.LANCZOS)
    if resized.mode not in {"RGB", "RGBA"}:
        return resized.convert("RGB")
    return resized


def _write_temp_png(image: Image.Image) -> Path:
    fd, temp_path = tempfile.mkstemp(prefix="igt_autocrop_", suffix=".png")
    os.close(fd)
    path = Path(temp_path)
    save_image = image
    if image.mode not in {"RGB", "RGBA"}:
        save_image = image.convert("RGB")
    save_image.save(path, format="PNG")
    return path
