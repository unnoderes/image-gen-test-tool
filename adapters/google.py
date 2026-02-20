import base64
import time
import uuid
from typing import Any, Dict, List, Optional

import requests

from adapters.base import ProviderAdapter
from core.io_utils import parse_input_image
from core.models import TASK_IMAGE2IMAGE, GenerationRequest, GenerationResponse


class GoogleAdapter(ProviderAdapter):
    provider = "google"

    def build_headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is missing")
        return {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        url = self._resolve_url(request.task_type)
        if "{model}" in url:
            url = url.format(model=request.model)
        payload = self.build_payload(request)
        headers = self.build_headers()

        started = time.perf_counter()
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout_seconds)
        latency_ms = int((time.perf_counter() - started) * 1000)
        raw = self._json_or_text(resp)

        if not resp.ok:
            raise RuntimeError(
                f"{self.provider} API error status={resp.status_code} body={str(raw)[:500]}"
            )

        return GenerationResponse(
            request_id=self.extract_request_id(raw),
            provider=request.provider,
            model=request.model,
            task_type=request.task_type,
            images=self.extract_images(raw),
            latency_ms=latency_ms,
            raw_response=raw,
        )

    def build_payload(self, request: GenerationRequest) -> Dict[str, Any]:
        parts: List[Dict[str, Any]] = [{"text": request.prompt}]
        if request.task_type == TASK_IMAGE2IMAGE:
            parts.append({"inline_data": self._to_inline_data(request.input_image)})

        payload: Dict[str, Any] = {
            "contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        }

        aspect_ratio = self._size_to_aspect_ratio(request.size)
        if aspect_ratio:
            payload["generationConfig"]["imageConfig"] = {"aspectRatio": aspect_ratio}

        if request.extra:
            payload.update(request.extra)
        return payload

    def extract_request_id(self, raw: Any) -> str:
        if isinstance(raw, dict):
            for key in ("request_id", "id", "task_id", "responseId"):
                value = raw.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return uuid.uuid4().hex[:12]

    def extract_images(self, raw: Any) -> List[str]:
        images = super().extract_images(raw)
        self._walk_inline_data(raw, images)
        deduped: List[str] = []
        seen = set()
        for item in images:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped

    def _walk_inline_data(self, node: Any, collector: List[str]) -> None:
        if isinstance(node, dict):
            for key in ("inlineData", "inline_data"):
                inline = node.get(key)
                if isinstance(inline, dict):
                    data = inline.get("data")
                    mime = inline.get("mimeType") or inline.get("mime_type") or "image/png"
                    if isinstance(data, str) and data:
                        collector.append(f"data:{mime};base64,{data}")
            for value in node.values():
                self._walk_inline_data(value, collector)
            return
        if isinstance(node, list):
            for item in node:
                self._walk_inline_data(item, collector)

    def _to_inline_data(self, input_image: Optional[str]) -> Dict[str, str]:
        image_info = parse_input_image(input_image)
        if not image_info:
            raise ValueError("input_image is required for image_to_image")

        if image_info["kind"] == "data_uri":
            return self._inline_from_data_uri(image_info["value"])

        if image_info["kind"] == "url":
            resp = requests.get(image_info["value"], timeout=self.timeout_seconds)
            resp.raise_for_status()
            mime = resp.headers.get("content-type", "image/png").split(";")[0]
            data = base64.b64encode(resp.content).decode("ascii")
            return {"mime_type": mime, "data": data}

        # Raw base64 fallback.
        return {"mime_type": "image/png", "data": image_info["value"]}

    def _inline_from_data_uri(self, value: str) -> Dict[str, str]:
        if "," not in value:
            raise ValueError("Invalid data URI for input_image")
        header, data = value.split(",", 1)
        mime = "image/png"
        if ":" in header and ";" in header:
            mime = header.split(":", 1)[1].split(";", 1)[0]
        return {"mime_type": mime, "data": data}

    def _json_or_text(self, response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {"raw_text": response.text}

    def _size_to_aspect_ratio(self, size: Optional[str]) -> Optional[str]:
        if not size:
            return None
        if "x" not in size:
            return None
        w_text, h_text = size.lower().split("x", 1)
        if not (w_text.isdigit() and h_text.isdigit()):
            return None
        width = int(w_text)
        height = int(h_text)
        if width <= 0 or height <= 0:
            return None
        ratio = _reduce_ratio(width, height)
        supported = {"1:1", "3:4", "4:3", "9:16", "16:9"}
        if ratio in supported:
            return ratio
        return None


def _reduce_ratio(width: int, height: int) -> str:
    left = width
    right = height
    while right:
        left, right = right, left % right
    return f"{width // left}:{height // left}"
