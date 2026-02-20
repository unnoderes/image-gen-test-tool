import pytest

from adapters.glm import GLMAdapter
from core.models import GenerationRequest


def test_glm_build_payload_text_to_image() -> None:
    adapter = GLMAdapter(
        api_key="test_key",
        text2image_url="https://open.bigmodel.cn/api/paas/v4/images/generations",
        image2image_url="https://open.bigmodel.cn/api/paas/v4/images/generations",
    )
    req = GenerationRequest(
        provider="glm",
        model="cogview-4-250304",
        task_type="text_to_image",
        prompt="A cute cat in watercolor style",
        size="1024x1024",
        n=2,
        seed=42,
    )
    payload = adapter.build_payload(req)
    assert payload["model"] == "cogview-4-250304"
    assert payload["prompt"] == "A cute cat in watercolor style"
    assert payload["size"] == "1024x1024"
    assert payload["n"] == 2
    assert payload["seed"] == 42


def test_glm_generate_success_extracts_image_url(requests_mock) -> None:
    adapter = GLMAdapter(
        api_key="test_key",
        text2image_url="https://open.bigmodel.cn/api/paas/v4/images/generations",
        image2image_url="https://open.bigmodel.cn/api/paas/v4/images/generations",
    )
    requests_mock.post(
        "https://open.bigmodel.cn/api/paas/v4/images/generations",
        json={"created": 123, "data": [{"url": "https://cdn.example.com/generated.png"}]},
        status_code=200,
    )
    req = GenerationRequest(
        provider="glm",
        model="cogview-4-250304",
        task_type="text_to_image",
        prompt="A city skyline at night",
    )
    resp = adapter.generate(req)
    assert resp.images == ["https://cdn.example.com/generated.png"]


def test_glm_missing_key_raises() -> None:
    adapter = GLMAdapter(
        api_key="",
        text2image_url="https://open.bigmodel.cn/api/paas/v4/images/generations",
        image2image_url="https://open.bigmodel.cn/api/paas/v4/images/generations",
    )
    req = GenerationRequest(
        provider="glm",
        model="cogview-4-250304",
        task_type="text_to_image",
        prompt="A city skyline at night",
    )
    with pytest.raises(ValueError, match="GLM_API_KEY"):
        adapter.generate(req)


def test_glm_build_payload_includes_negative_prompt_when_set() -> None:
    adapter = GLMAdapter(
        api_key="test_key",
        text2image_url="https://open.bigmodel.cn/api/paas/v4/images/generations",
        image2image_url="https://open.bigmodel.cn/api/paas/v4/images/generations",
    )
    req = GenerationRequest(
        provider="glm",
        model="glm-image",
        task_type="text_to_image",
        prompt="A city skyline",
        negative_prompt="blur, artifacts",
    )
    payload = adapter.build_payload(req)
    assert payload["negative_prompt"] == "blur, artifacts"
