import pytest
from pydantic import ValidationError

from core.models import GenerationRequest


def test_text_to_image_request_is_valid() -> None:
    req = GenerationRequest(
        provider="alibaba",
        model="wanx-v1",
        task_type="text_to_image",
        prompt="A red sports car",
    )
    assert req.provider == "alibaba"
    assert req.n == 1


def test_image_to_image_requires_input_image() -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(
            provider="google",
            model="imagen-3",
            task_type="image_to_image",
            prompt="Turn into sketch style",
        )


def test_provider_must_be_supported() -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(
            provider="other",
            model="x",
            task_type="text_to_image",
            prompt="test",
        )


def test_negative_prompt_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(
            provider="alibaba",
            model="qwen-image-max",
            task_type="text_to_image",
            prompt="test",
            negative_prompt="   ",
        )
