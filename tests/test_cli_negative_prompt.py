import pytest

from cli import _build_parser, _request_from_args


def test_parser_accepts_negative_prompt_flags() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "single",
            "--provider",
            "alibaba",
            "--model",
            "qwen-image-max",
            "--task-type",
            "text_to_image",
            "--prompt",
            "x",
            "--negative-prompt-enabled",
            "on",
            "--negative-prompt",
            "bad anatomy",
        ]
    )
    assert args.negative_prompt_enabled == "on"
    assert args.negative_prompt == "bad anatomy"


def test_request_from_args_sets_negative_prompt_when_enabled() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "single",
            "--provider",
            "alibaba",
            "--model",
            "qwen-image-max",
            "--task-type",
            "text_to_image",
            "--prompt",
            "x",
            "--negative-prompt-enabled",
            "on",
            "--negative-prompt",
            "bad anatomy",
        ]
    )
    request = _request_from_args(args)
    assert request.negative_prompt == "bad anatomy"


def test_request_from_args_ignores_negative_prompt_when_disabled() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "single",
            "--provider",
            "alibaba",
            "--model",
            "qwen-image-max",
            "--task-type",
            "text_to_image",
            "--prompt",
            "x",
            "--negative-prompt-enabled",
            "off",
            "--negative-prompt",
            "bad anatomy",
        ]
    )
    request = _request_from_args(args)
    assert request.negative_prompt is None


def test_request_from_args_requires_negative_prompt_when_enabled() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "single",
            "--provider",
            "alibaba",
            "--model",
            "qwen-image-max",
            "--task-type",
            "text_to_image",
            "--prompt",
            "x",
            "--negative-prompt-enabled",
            "on",
        ]
    )
    with pytest.raises(ValueError, match="negative_prompt is required"):
        _request_from_args(args)
