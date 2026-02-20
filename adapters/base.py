import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List

import requests

from core.models import GenerationRequest, GenerationResponse


class ProviderAdapter(ABC):
    provider: str

    def __init__(
        self,
        api_key: str,
        text2image_url: str,
        image2image_url: str,
        timeout_seconds: int = 120,
    ):
        self.api_key = api_key
        self.text2image_url = text2image_url
        self.image2image_url = image2image_url
        self.timeout_seconds = timeout_seconds

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        url = self._resolve_url(request.task_type)
        payload = self.build_payload(request)
        headers = self.build_headers()
        started = time.perf_counter()
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout_seconds)
        latency_ms = int((time.perf_counter() - started) * 1000)

        raw: Any
        try:
            raw = resp.json()
        except ValueError:
            raw = {"raw_text": resp.text}

        if not resp.ok:
            error_preview = str(raw)[:500]
            raise RuntimeError(
                f"{self.provider} API error status={resp.status_code} body={error_preview}"
            )

        images = self.extract_images(raw)
        return GenerationResponse(
            request_id=self.extract_request_id(raw),
            provider=request.provider,
            model=request.model,
            task_type=request.task_type,
            images=images,
            latency_ms=latency_ms,
            raw_response=raw,
        )

    def _resolve_url(self, task_type: str) -> str:
        if task_type == "text_to_image":
            target = self.text2image_url
        elif task_type == "image_to_image":
            target = self.image2image_url
        else:
            raise ValueError(f"Unsupported task_type: {task_type}")
        if not target:
            raise ValueError(f"Missing endpoint URL for {self.provider}:{task_type}")
        return target

    def extract_request_id(self, raw: Any) -> str:
        if isinstance(raw, dict):
            for key in ("request_id", "id", "task_id"):
                value = raw.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return uuid.uuid4().hex[:12]

    def extract_images(self, raw: Any) -> List[str]:
        if not raw:
            return []
        results: List[str] = []
        self._walk_and_collect(raw, results)
        deduped = []
        seen = set()
        for item in results:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped

    def _walk_and_collect(self, node: Any, collector: List[str]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, str) and self._looks_like_image(key, value):
                    collector.append(value)
                else:
                    self._walk_and_collect(value, collector)
            return

        if isinstance(node, list):
            for item in node:
                self._walk_and_collect(item, collector)

    def _looks_like_image(self, key: str, value: str) -> bool:
        low_key = key.lower()
        low_val = value.lower()
        if low_val.startswith("http://") or low_val.startswith("https://"):
            return any(
                mark in low_key
                for mark in ("image", "img", "url", "output", "result", "generated")
            )
        if low_val.startswith("data:image/"):
            return True
        if "b64" in low_key or "base64" in low_key:
            return len(value) > 100
        return False

    @abstractmethod
    def build_headers(self) -> Dict[str, str]:
        raise NotImplementedError

    @abstractmethod
    def build_payload(self, request: GenerationRequest) -> Dict[str, Any]:
        raise NotImplementedError
