from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TASK_TEXT2IMAGE = "text_to_image"
TASK_IMAGE2IMAGE = "image_to_image"
ProviderType = Literal["alibaba", "google", "glm"]
TaskType = Literal[TASK_TEXT2IMAGE, TASK_IMAGE2IMAGE]


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderType
    model: str = Field(min_length=1)
    task_type: TaskType
    prompt: str = Field(min_length=1)
    negative_prompt: Optional[str] = None
    input_image: Optional[str] = None
    size: Optional[str] = None
    n: int = Field(default=1, ge=1)
    seed: Optional[int] = None
    extra: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("model", "prompt")
    @classmethod
    def ensure_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator("size")
    @classmethod
    def ensure_size_non_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("size must not be blank")
        return value

    @field_validator("negative_prompt")
    @classmethod
    def ensure_negative_prompt_non_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("negative_prompt must not be blank")
        return value

    @model_validator(mode="after")
    def ensure_task_fields(self) -> "GenerationRequest":
        if self.task_type == TASK_IMAGE2IMAGE and not self.input_image:
            raise ValueError("input_image is required for image_to_image")
        return self

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class GenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    provider: ProviderType
    model: str
    task_type: TaskType
    images: List[str]
    latency_ms: int = Field(ge=0)
    raw_response: Any

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
