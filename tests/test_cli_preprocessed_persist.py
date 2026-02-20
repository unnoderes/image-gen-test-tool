import os

from cli import _apply_cli_env_overrides, _build_parser
from core.runner import PERSIST_PREPROCESSED_INPUT_ENV
from core.services import ALIBABA_AUTOCROP_ENV


def test_parser_accepts_persist_preprocessed_input_flag() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "--persist-preprocessed-input",
            "on",
            "single",
            "--provider",
            "alibaba",
            "--model",
            "qwen-image-edit",
            "--task-type",
            "image_to_image",
            "--prompt",
            "x",
            "--input-image",
            "input.png",
        ]
    )
    assert args.persist_preprocessed_input == "on"


def test_apply_cli_env_overrides_sets_persist_flag(monkeypatch) -> None:
    class Args:
        auto_crop = None
        persist_preprocessed_input = "off"

    monkeypatch.setenv(PERSIST_PREPROCESSED_INPUT_ENV, "true")
    _apply_cli_env_overrides(Args())
    assert os.environ[PERSIST_PREPROCESSED_INPUT_ENV] == "false"


def test_parser_accepts_auto_crop_flag() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "--auto-crop",
            "off",
            "single",
            "--provider",
            "alibaba",
            "--model",
            "qwen-image-edit",
            "--task-type",
            "image_to_image",
            "--prompt",
            "x",
            "--input-image",
            "input.png",
        ]
    )
    assert args.auto_crop == "off"


def test_apply_cli_env_overrides_sets_auto_crop_flag(monkeypatch) -> None:
    class Args:
        auto_crop = "off"
        persist_preprocessed_input = None

    monkeypatch.setenv(ALIBABA_AUTOCROP_ENV, "on")
    _apply_cli_env_overrides(Args())
    assert os.environ[ALIBABA_AUTOCROP_ENV] == "off"
