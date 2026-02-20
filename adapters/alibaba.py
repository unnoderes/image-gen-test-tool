import time
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import requests

from adapters.base import ProviderAdapter
from core.io_utils import parse_input_image
from core.models import TASK_IMAGE2IMAGE, GenerationRequest, GenerationResponse


class AlibabaAdapter(ProviderAdapter):
    provider = "alibaba"

    def __init__(
        self,
        api_key: str,
        text2image_url: str,
        image2image_url: str,
        timeout_seconds: int = 120,
        async_mode: bool = False,
        async_url: str = "",
        poll_interval_seconds: int = 10,
        poll_timeout_seconds: int = 300,
    ):
        super().__init__(
            api_key=api_key,
            text2image_url=text2image_url,
            image2image_url=image2image_url,
            timeout_seconds=timeout_seconds,
        )
        self.async_mode = async_mode
        self.async_url = async_url
        self.poll_interval_seconds = poll_interval_seconds
        self.poll_timeout_seconds = poll_timeout_seconds

    def build_headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise ValueError("ALIBABA_API_KEY is missing")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        if self.async_mode:
            return self._generate_async(request)
        try:
            return super().generate(request)
        except RuntimeError as exc:
            if "does not support synchronous calls" in str(exc):
                return self._generate_async(request)
            raise

    def build_payload(self, request: GenerationRequest) -> Dict[str, Any]:
        content = [{"text": request.prompt}]
        image_info = parse_input_image(request.input_image)
        if image_info:
            content.append({"image": image_info["value"]})

        enable_interleave = request.task_type != TASK_IMAGE2IMAGE
        parameters: Dict[str, Any] = {
            "enable_interleave": enable_interleave,
            "watermark": False,
        }
        if request.size:
            parameters["size"] = request.size.replace("x", "*")

        if enable_interleave:
            # For text-to-image, this family typically uses max_images.
            parameters["max_images"] = request.n
        else:
            parameters["n"] = request.n

        if request.seed is not None:
            parameters["seed"] = request.seed
        if request.negative_prompt:
            parameters["negative_prompt"] = request.negative_prompt

        payload: Dict[str, Any] = {
            "model": request.model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": parameters,
        }

        # Allow one-level override for rapid experimentation.
        if request.extra:
            payload.update(request.extra)
        return payload

    def _generate_async(self, request: GenerationRequest) -> GenerationResponse:
        create_url = self.async_url or self._derive_async_url(self._resolve_url(request.task_type))
        payload = self.build_payload(request)
        headers = self.build_headers()
        headers["X-DashScope-Async"] = "enable"

        started = time.perf_counter()
        create_resp = requests.post(
            create_url,
            headers=headers,
            json=payload,
            timeout=self.timeout_seconds,
        )
        create_raw = self._json_or_text(create_resp)
        if not create_resp.ok:
            raise RuntimeError(
                f"{self.provider} async create error status={create_resp.status_code} "
                f"body={str(create_raw)[:500]}"
            )

        task_id = self._extract_task_id(create_raw)
        if not task_id:
            raise RuntimeError(f"{self.provider} async create missing task_id: {create_raw}")

        task_url = self._build_task_url(create_url, task_id)
        final_raw = self._poll_task(task_url, headers)
        latency_ms = int((time.perf_counter() - started) * 1000)

        return GenerationResponse(
            request_id=task_id,
            provider=request.provider,
            model=request.model,
            task_type=request.task_type,
            images=self.extract_images(final_raw),
            latency_ms=latency_ms,
            raw_response={"create_task": create_raw, "task_result": final_raw},
        )

    def _poll_task(self, task_url: str, headers: Dict[str, str]) -> Any:
        deadline = time.monotonic() + self.poll_timeout_seconds
        while time.monotonic() < deadline:
            poll_resp = requests.get(task_url, headers=headers, timeout=self.timeout_seconds)
            poll_raw = self._json_or_text(poll_resp)
            if not poll_resp.ok:
                raise RuntimeError(
                    f"{self.provider} async poll error status={poll_resp.status_code} "
                    f"body={str(poll_raw)[:500]}"
                )

            status = self._extract_task_status(poll_raw)
            if status in {"SUCCEEDED", "SUCCESS"}:
                return poll_raw
            if status in {"FAILED", "CANCELED", "CANCELLED"}:
                raise RuntimeError(f"{self.provider} async task failed: {poll_raw}")
            time.sleep(self.poll_interval_seconds)

        raise TimeoutError(
            f"{self.provider} async task poll timeout after {self.poll_timeout_seconds}s"
        )

    def _extract_task_id(self, raw: Any) -> Optional[str]:
        if isinstance(raw, dict):
            output = raw.get("output")
            if isinstance(output, dict):
                value = output.get("task_id")
                if isinstance(value, str) and value.strip():
                    return value.strip()
            value = raw.get("task_id")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _extract_task_status(self, raw: Any) -> str:
        if isinstance(raw, dict):
            output = raw.get("output")
            if isinstance(output, dict):
                value = output.get("task_status")
                if isinstance(value, str):
                    return value.upper()
            value = raw.get("task_status")
            if isinstance(value, str):
                return value.upper()
        return "UNKNOWN"

    def _build_task_url(self, create_url: str, task_id: str) -> str:
        parts = urlsplit(create_url)
        return f"{parts.scheme}://{parts.netloc}/api/v1/tasks/{task_id}"

    def _derive_async_url(self, url: str) -> str:
        return url.replace("/multimodal-generation/", "/image-generation/")

    def _json_or_text(self, response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {"raw_text": response.text}
