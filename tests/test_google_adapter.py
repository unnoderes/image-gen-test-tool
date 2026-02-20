import pytest

from adapters.google import GoogleAdapter
from core.models import GenerationRequest


def test_google_build_payload_image_to_image() -> None:
    adapter = GoogleAdapter(
        api_key="test_key",
        text2image_url="https://api.example.com/t2i",
        image2image_url="https://api.example.com/i2i",
    )
    req = GenerationRequest(
        provider="google",
        model="imagen-3",
        task_type="image_to_image",
        prompt="Turn into cartoon",
        input_image="data:image/png;base64,aGVsbG8=",
        n=1,
    )
    payload = adapter.build_payload(req)
    assert payload["contents"][0]["parts"][0]["text"] == "Turn into cartoon"
    assert payload["contents"][0]["parts"][1]["inline_data"]["mime_type"] == "image/png"
    assert payload["contents"][0]["parts"][1]["inline_data"]["data"] == "aGVsbG8="
    assert payload["generationConfig"]["responseModalities"] == ["IMAGE"]


def test_google_generate_success_extracts_inline_data(requests_mock) -> None:
    adapter = GoogleAdapter(
        api_key="test_key",
        text2image_url="https://api.example.com/models/{model}:generateContent",
        image2image_url="https://api.example.com/models/{model}:generateContent",
    )
    requests_mock.post(
        "https://api.example.com/models/gemini-2.5-flash-image:generateContent",
        json={
            "responseId": "resp_1",
            "candidates": [
                {
                    "content": {
                        "parts": [{"inlineData": {"mimeType": "image/png", "data": "aGVsbG8="}}]
                    }
                }
            ],
        },
        status_code=200,
    )
    req = GenerationRequest(
        provider="google",
        model="gemini-2.5-flash-image",
        task_type="text_to_image",
        prompt="A house",
    )
    resp = adapter.generate(req)
    assert resp.request_id == "resp_1"
    assert resp.images == ["data:image/png;base64,aGVsbG8="]


def test_google_generate_error_raises(requests_mock) -> None:
    adapter = GoogleAdapter(
        api_key="test_key",
        text2image_url="https://api.example.com/models/{model}:generateContent",
        image2image_url="https://api.example.com/models/{model}:generateContent",
    )
    requests_mock.post(
        "https://api.example.com/models/gemini-2.5-flash-image:generateContent",
        json={"error": {"message": "bad request"}},
        status_code=400,
    )
    req = GenerationRequest(
        provider="google",
        model="gemini-2.5-flash-image",
        task_type="text_to_image",
        prompt="A house",
    )
    with pytest.raises(RuntimeError, match="google API error"):
        adapter.generate(req)


def test_google_missing_key_raises() -> None:
    adapter = GoogleAdapter(
        api_key="",
        text2image_url="https://api.example.com/models/{model}:generateContent",
        image2image_url="https://api.example.com/models/{model}:generateContent",
    )
    req = GenerationRequest(
        provider="google",
        model="gemini-2.5-flash-image",
        task_type="text_to_image",
        prompt="A house",
    )
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        adapter.generate(req)
