from pathlib import Path

import pytest
from PIL import Image

from core.models import GenerationRequest, GenerationResponse
from core.runner import (
    cleanup_temp_files,
    persist_run,
    run_with_retry,
    run_with_retry_with_artifacts,
    save_images,
    summarize_results,
)


class FlakyAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary failure")
        return GenerationResponse(
            request_id="req_123",
            provider=request.provider,
            model=request.model,
            task_type=request.task_type,
            images=["data:image/png;base64,aGVsbG8="],
            latency_ms=20,
            raw_response={"ok": True},
        )


def test_run_with_retry_eventually_succeeds() -> None:
    adapter = FlakyAdapter()
    req = GenerationRequest(
        provider="alibaba",
        model="wanx-v1",
        task_type="text_to_image",
        prompt="A cat",
    )
    resp = run_with_retry(adapter, req, max_retries=1, retry_delay_seconds=0)
    assert resp.request_id == "req_123"
    assert adapter.calls == 2


def test_persist_run_writes_files(tmp_path: Path) -> None:
    req = GenerationRequest(
        provider="google",
        model="imagen-3",
        task_type="text_to_image",
        prompt="A tree",
    )
    resp = GenerationResponse(
        request_id="req_x",
        provider="google",
        model="imagen-3",
        task_type="text_to_image",
        images=["data:image/png;base64,aGVsbG8="],
        latency_ms=10,
        raw_response={"id": "req_x"},
    )
    run_dir = persist_run(tmp_path, req, resp)
    assert (run_dir / "request.json").exists()
    assert (run_dir / "response.json").exists()
    assert (run_dir / "saved_images.json").exists()
    assert (run_dir / "images").exists()


def test_summarize_results_creates_csv(tmp_path: Path) -> None:
    output = tmp_path / "summary.csv"
    summarize_results(
        [
            {
                "provider": "alibaba",
                "model": "wanx-v1",
                "prompt": 'A "quoted" prompt',
                "status": "ok",
                "run_dir": "runs/x",
                "error": "",
            }
        ],
        output,
    )
    content = output.read_text(encoding="utf-8")
    assert "provider,model,prompt,status,run_dir,error" in content
    assert '"A ""quoted"" prompt"' in content


def test_save_images_keeps_bin_and_creates_png_alias_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DummyResponse:
        content = b"fake-image-bytes"

        @staticmethod
        def raise_for_status() -> None:
            return None

    def _fake_get(url: str, timeout: int):  # noqa: ANN001, ARG001
        return DummyResponse()

    monkeypatch.delenv("IGT_BIN_ALIAS_FORMAT", raising=False)
    monkeypatch.setattr("core.runner.requests.get", _fake_get)
    saved = save_images(tmp_path, ["https://example.com/image.bin"])
    assert any(item.endswith(".bin") for item in saved)
    assert any(item.endswith(".png") for item in saved)


def test_save_images_keeps_bin_and_creates_jpg_alias_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DummyResponse:
        content = b"fake-image-bytes"

        @staticmethod
        def raise_for_status() -> None:
            return None

    def _fake_get(url: str, timeout: int):  # noqa: ANN001, ARG001
        return DummyResponse()

    monkeypatch.setenv("IGT_BIN_ALIAS_FORMAT", "jpg")
    monkeypatch.setattr("core.runner.requests.get", _fake_get)
    saved = save_images(tmp_path, ["https://example.com/image.bin"])
    assert any(item.endswith(".bin") for item in saved)
    assert any(item.endswith(".jpg") for item in saved)


def test_run_with_retry_cleans_autocrop_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (1600, 1200), color=(120, 20, 20)).save(source, format="PNG")
    monkeypatch.setenv("IGT_ALIBABA_IMAGE2IMAGE_AUTOCROP", "on")
    request = GenerationRequest(
        provider="alibaba",
        model="qwen-image-edit",
        task_type="image_to_image",
        prompt="anime style",
        input_image=str(source),
        size="1024x1024",
    )
    received_path: dict[str, Path] = {}

    class DummyAdapter:
        @staticmethod
        def generate(req: GenerationRequest) -> GenerationResponse:
            path = Path(req.input_image or "")
            received_path["value"] = path
            assert path.exists()
            return GenerationResponse(
                request_id="req_autocrop",
                provider=req.provider,
                model=req.model,
                task_type=req.task_type,
                images=["data:image/png;base64,aGVsbG8="],
                latency_ms=10,
                raw_response={"ok": True},
            )

    run_with_retry(DummyAdapter(), request, max_retries=0, retry_delay_seconds=0)
    assert "value" in received_path
    assert received_path["value"] != source
    assert not received_path["value"].exists()


def test_run_with_retry_with_artifacts_returns_autocrop_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (1600, 1200), color=(120, 20, 20)).save(source, format="PNG")
    monkeypatch.setenv("IGT_ALIBABA_IMAGE2IMAGE_AUTOCROP", "on")
    request = GenerationRequest(
        provider="alibaba",
        model="qwen-image-edit",
        task_type="image_to_image",
        prompt="anime style",
        input_image=str(source),
        size="1024x1024",
    )

    class DummyAdapter:
        @staticmethod
        def generate(req: GenerationRequest) -> GenerationResponse:
            return GenerationResponse(
                request_id="req_autocrop",
                provider=req.provider,
                model=req.model,
                task_type=req.task_type,
                images=["data:image/png;base64,aGVsbG8="],
                latency_ms=10,
                raw_response={"ok": True},
            )

    _, preprocessed_inputs = run_with_retry_with_artifacts(
        DummyAdapter(),
        request,
        max_retries=0,
        retry_delay_seconds=0,
    )
    assert len(preprocessed_inputs) == 1
    assert preprocessed_inputs[0].exists()
    cleanup_temp_files(preprocessed_inputs)
    assert not preprocessed_inputs[0].exists()


def test_persist_run_saves_preprocessed_inputs_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = GenerationRequest(
        provider="alibaba",
        model="qwen-image-edit",
        task_type="image_to_image",
        prompt="anime style",
        input_image="dummy.png",
        size="1024x1024",
    )
    response = GenerationResponse(
        request_id="req_pre",
        provider="alibaba",
        model="qwen-image-edit",
        task_type="image_to_image",
        images=["data:image/png;base64,aGVsbG8="],
        latency_ms=10,
        raw_response={"id": "req_pre"},
    )
    preprocessed = tmp_path / "preprocessed.png"
    Image.new("RGB", (1024, 1024), color=(10, 20, 30)).save(preprocessed, format="PNG")
    monkeypatch.setenv("IGT_PERSIST_PREPROCESSED_INPUT", "on")

    run_dir = persist_run(
        tmp_path,
        request,
        response,
        preprocessed_inputs=[preprocessed],
    )
    assert (run_dir / "preprocessed_inputs.json").exists()
    assert (run_dir / "preprocessed_inputs" / "input_01.png").exists()


def test_persist_run_skips_preprocessed_inputs_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = GenerationRequest(
        provider="alibaba",
        model="qwen-image-edit",
        task_type="image_to_image",
        prompt="anime style",
        input_image="dummy.png",
        size="1024x1024",
    )
    response = GenerationResponse(
        request_id="req_pre_off",
        provider="alibaba",
        model="qwen-image-edit",
        task_type="image_to_image",
        images=["data:image/png;base64,aGVsbG8="],
        latency_ms=10,
        raw_response={"id": "req_pre_off"},
    )
    preprocessed = tmp_path / "preprocessed-off.png"
    Image.new("RGB", (1024, 1024), color=(30, 20, 10)).save(preprocessed, format="PNG")
    monkeypatch.setenv("IGT_PERSIST_PREPROCESSED_INPUT", "off")

    run_dir = persist_run(
        tmp_path,
        request,
        response,
        preprocessed_inputs=[preprocessed],
    )
    assert not (run_dir / "preprocessed_inputs.json").exists()
