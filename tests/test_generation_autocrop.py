from pathlib import Path

import pytest
from PIL import Image

from core.models import GenerationRequest
from core.services.generation import prepare_request_for_execution


def _write_png(path: Path, width: int, height: int) -> None:
    Image.new("RGB", (width, height), color=(200, 50, 50)).save(path, format="PNG")


def _read_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def test_prepare_request_for_execution_skips_non_alibaba(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    _write_png(source, 1600, 1200)
    request = GenerationRequest(
        provider="google",
        model="gemini-2.5-flash-image",
        task_type="image_to_image",
        prompt="anime style",
        input_image=str(source),
        size="1024x1024",
    )
    prepared, cleanup = prepare_request_for_execution(request)
    assert prepared is request
    assert cleanup == []


def test_prepare_request_for_execution_autocrops_large_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "large.png"
    _write_png(source, 3242, 2160)
    monkeypatch.setenv("IGT_ALIBABA_IMAGE2IMAGE_AUTOCROP", "on")
    request = GenerationRequest(
        provider="alibaba",
        model="qwen-image-edit",
        task_type="image_to_image",
        prompt="anime style",
        input_image=str(source),
        size="3242x2160",
    )
    prepared, cleanup = prepare_request_for_execution(request)
    assert prepared.size == "2048x1364"
    assert len(cleanup) == 1
    assert prepared.input_image != str(source)
    output_path = Path(prepared.input_image or "")
    assert output_path.exists()
    assert _read_size(output_path) == (2048, 1364)
    output_path.unlink(missing_ok=True)


def test_prepare_request_for_execution_autocrops_to_explicit_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.png"
    _write_png(source, 1600, 1200)
    monkeypatch.setenv("IGT_ALIBABA_IMAGE2IMAGE_AUTOCROP", "on")
    request = GenerationRequest(
        provider="alibaba",
        model="qwen-image-edit",
        task_type="image_to_image",
        prompt="anime style",
        input_image=str(source),
        size="1024x1024",
    )
    prepared, cleanup = prepare_request_for_execution(request)
    assert prepared.size == "1024x1024"
    assert len(cleanup) == 1
    output_path = Path(prepared.input_image or "")
    assert output_path.exists()
    assert _read_size(output_path) == (1024, 1024)
    output_path.unlink(missing_ok=True)


def test_prepare_request_for_execution_same_size_no_persist_returns_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "same.png"
    _write_png(source, 1024, 1024)
    monkeypatch.setenv("IGT_ALIBABA_IMAGE2IMAGE_AUTOCROP", "on")
    monkeypatch.setenv("IGT_PERSIST_PREPROCESSED_INPUT", "off")
    request = GenerationRequest(
        provider="alibaba",
        model="qwen-image-edit",
        task_type="image_to_image",
        prompt="anime style",
        input_image=str(source),
        size="1024x1024",
    )
    prepared, cleanup = prepare_request_for_execution(request)
    assert prepared.size == "1024x1024"
    assert prepared.input_image == str(source)
    assert cleanup == []


def test_prepare_request_for_execution_same_size_with_persist_returns_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "same.png"
    _write_png(source, 1024, 1024)
    monkeypatch.setenv("IGT_ALIBABA_IMAGE2IMAGE_AUTOCROP", "on")
    monkeypatch.setenv("IGT_PERSIST_PREPROCESSED_INPUT", "on")
    request = GenerationRequest(
        provider="alibaba",
        model="qwen-image-edit",
        task_type="image_to_image",
        prompt="anime style",
        input_image=str(source),
        size="1024x1024",
    )
    prepared, cleanup = prepare_request_for_execution(request)
    assert prepared.size == "1024x1024"
    assert len(cleanup) == 1
    output_path = Path(prepared.input_image or "")
    assert output_path.exists()
    assert output_path != source
    assert _read_size(output_path) == (1024, 1024)
    output_path.unlink(missing_ok=True)


def test_prepare_request_for_execution_autocrop_disabled_skips_processing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "large.png"
    _write_png(source, 3242, 2160)
    monkeypatch.setenv("IGT_ALIBABA_IMAGE2IMAGE_AUTOCROP", "off")
    request = GenerationRequest(
        provider="alibaba",
        model="qwen-image-edit",
        task_type="image_to_image",
        prompt="anime style",
        input_image=str(source),
        size=None,
    )
    prepared, cleanup = prepare_request_for_execution(request)
    assert prepared is request
    assert prepared.size is None
    assert prepared.input_image == str(source)
    assert cleanup == []


def test_prepare_request_for_execution_autocrop_default_off_skips_processing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "large-default-off.png"
    _write_png(source, 3242, 2160)
    monkeypatch.delenv("IGT_ALIBABA_IMAGE2IMAGE_AUTOCROP", raising=False)
    request = GenerationRequest(
        provider="alibaba",
        model="qwen-image-edit",
        task_type="image_to_image",
        prompt="anime style",
        input_image=str(source),
        size=None,
    )
    prepared, cleanup = prepare_request_for_execution(request)
    assert prepared is request
    assert prepared.size is None
    assert prepared.input_image == str(source)
    assert cleanup == []
