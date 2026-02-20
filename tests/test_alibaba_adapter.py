import pytest

from adapters.alibaba import AlibabaAdapter
from core.models import GenerationRequest


def test_alibaba_build_payload_text_to_image() -> None:
    adapter = AlibabaAdapter(
        api_key="test_key",
        text2image_url="https://api.example.com/t2i",
        image2image_url="https://api.example.com/i2i",
    )
    req = GenerationRequest(
        provider="alibaba",
        model="wanx-v1",
        task_type="text_to_image",
        prompt="A snowy mountain",
        size="1024x1024",
        n=2,
        seed=7,
    )
    payload = adapter.build_payload(req)
    assert payload["model"] == "wanx-v1"
    assert payload["input"]["messages"][0]["content"][0]["text"] == "A snowy mountain"
    assert payload["parameters"]["size"] == "1024*1024"
    assert payload["parameters"]["max_images"] == 2
    assert payload["parameters"]["seed"] == 7


def test_alibaba_generate_success_extracts_images(requests_mock) -> None:
    adapter = AlibabaAdapter(
        api_key="test_key",
        text2image_url="https://api.example.com/t2i",
        image2image_url="https://api.example.com/i2i",
    )
    requests_mock.post(
        "https://api.example.com/t2i",
        json={"id": "req_1", "output": {"image_url": "https://cdn.example.com/a.png"}},
        status_code=200,
    )
    req = GenerationRequest(
        provider="alibaba",
        model="wanx-v1",
        task_type="text_to_image",
        prompt="A robot",
    )
    resp = adapter.generate(req)
    assert resp.request_id == "req_1"
    assert resp.images == ["https://cdn.example.com/a.png"]


def test_alibaba_async_generate_polls_task(requests_mock) -> None:
    adapter = AlibabaAdapter(
        api_key="test_key",
        text2image_url="https://api.example.com/sync",
        image2image_url="https://api.example.com/sync",
        async_mode=True,
        async_url="https://api.example.com/async",
        poll_interval_seconds=0,
        poll_timeout_seconds=1,
    )
    requests_mock.post(
        "https://api.example.com/async",
        json={"output": {"task_id": "task_1"}},
        status_code=200,
    )
    requests_mock.get(
        "https://api.example.com/api/v1/tasks/task_1",
        json={
            "output": {"task_status": "SUCCEEDED"},
            "result": {"image_url": "https://cdn.example.com/async.png"},
        },
        status_code=200,
    )
    req = GenerationRequest(
        provider="alibaba",
        model="wanx-v1",
        task_type="text_to_image",
        prompt="A robot",
    )
    resp = adapter.generate(req)
    assert resp.request_id == "task_1"
    assert resp.images == ["https://cdn.example.com/async.png"]


def test_alibaba_missing_key_raises() -> None:
    adapter = AlibabaAdapter(
        api_key="",
        text2image_url="https://api.example.com/t2i",
        image2image_url="https://api.example.com/i2i",
    )
    req = GenerationRequest(
        provider="alibaba",
        model="wanx-v1",
        task_type="text_to_image",
        prompt="A robot",
    )
    with pytest.raises(ValueError, match="ALIBABA_API_KEY"):
        adapter.generate(req)


def test_alibaba_build_payload_includes_negative_prompt_when_set() -> None:
    adapter = AlibabaAdapter(
        api_key="test_key",
        text2image_url="https://api.example.com/t2i",
        image2image_url="https://api.example.com/i2i",
    )
    req = GenerationRequest(
        provider="alibaba",
        model="qwen-image-max",
        task_type="text_to_image",
        prompt="A robot",
        negative_prompt="blurry, low quality",
    )
    payload = adapter.build_payload(req)
    assert payload["parameters"]["negative_prompt"] == "blurry, low quality"
