from argparse import Namespace

import pytest

from cli import _resolve_compare_targets


def _args(**kwargs):
    base = {
        "provider_a": None,
        "model_a": None,
        "provider_b": None,
        "model_b": None,
        "model_alibaba": None,
        "model_google": None,
    }
    base.update(kwargs)
    return Namespace(**base)


def test_compare_new_mode_targets() -> None:
    args = _args(
        provider_a="alibaba",
        model_a="qwen-image",
        provider_b="glm",
        model_b="cogview-4-250304",
    )
    assert _resolve_compare_targets(args) == [
        ("alibaba", "qwen-image"),
        ("glm", "cogview-4-250304"),
    ]


def test_compare_legacy_mode_targets() -> None:
    args = _args(model_alibaba="qwen-image", model_google="gemini-2.5-flash-image")
    assert _resolve_compare_targets(args) == [
        ("alibaba", "qwen-image"),
        ("google", "gemini-2.5-flash-image"),
    ]


def test_compare_mixed_mode_raises() -> None:
    args = _args(
        provider_a="alibaba",
        model_a="qwen-image",
        provider_b="google",
        model_b="gemini-2.5-flash-image",
        model_alibaba="qwen-image",
        model_google="gemini-2.5-flash-image",
    )
    with pytest.raises(ValueError, match="not both"):
        _resolve_compare_targets(args)


def test_compare_incomplete_new_mode_raises() -> None:
    args = _args(provider_a="alibaba", model_a="qwen-image")
    with pytest.raises(ValueError, match="missing args"):
        _resolve_compare_targets(args)
