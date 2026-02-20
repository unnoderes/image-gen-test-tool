from typing import Any, Dict

from adapters.base import ProviderAdapter
from core.io_utils import parse_input_image
from core.models import TASK_IMAGE2IMAGE, GenerationRequest


class GLMAdapter(ProviderAdapter):
    provider = "glm"

    def build_headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise ValueError("GLM_API_KEY is missing")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def build_payload(self, request: GenerationRequest) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": request.model,
            "prompt": request.prompt,
        }
        if request.size:
            payload["size"] = request.size
        if request.n > 1:
            payload["n"] = request.n
        if request.seed is not None:
            payload["seed"] = request.seed
        if request.negative_prompt:
            payload["negative_prompt"] = request.negative_prompt

        # Some GLM image models accept source image URL/Base64 for editing workflows.
        if request.task_type == TASK_IMAGE2IMAGE:
            image_info = parse_input_image(request.input_image)
            if image_info:
                payload["image_url"] = image_info["value"]

        if request.extra:
            payload.update(request.extra)
        return payload
