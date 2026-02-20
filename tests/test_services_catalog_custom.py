from pathlib import Path

import pytest

from core.models import TASK_IMAGE2IMAGE, TASK_TEXT2IMAGE
from core.services.catalog import (
    add_custom_model_entry,
    delete_custom_model_entry,
    list_model_entries,
)


def test_add_custom_model_entry_and_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    custom_path = tmp_path / "custom_models.json"
    monkeypatch.setenv("IGT_CUSTOM_MODELS_PATH", str(custom_path))
    added = add_custom_model_entry(
        provider="alibaba",
        model_id="my-qwen-custom-001",
        task_type=TASK_TEXT2IMAGE,
        recommended=None,
    )
    assert added["provider"] == "alibaba"
    assert added["status"] == "custom"
    rows = list_model_entries(provider="alibaba", task_type=TASK_TEXT2IMAGE, recommend_only=False)
    assert any(item["id"] == "my-qwen-custom-001" for item in rows)


def test_add_custom_model_entry_recommended(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    custom_path = tmp_path / "custom_models.json"
    monkeypatch.setenv("IGT_CUSTOM_MODELS_PATH", str(custom_path))
    added = add_custom_model_entry(
        provider="google",
        model_id="my-gemini-custom-001",
        task_type=TASK_IMAGE2IMAGE,
        recommended=True,
    )
    assert added["status"] == "recommended"
    rows = list_model_entries(provider="google", task_type=TASK_IMAGE2IMAGE, recommend_only=True)
    assert any(item["id"] == "my-gemini-custom-001" for item in rows)


def test_add_custom_model_entry_unsupported_provider_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    custom_path = tmp_path / "custom_models.json"
    monkeypatch.setenv("IGT_CUSTOM_MODELS_PATH", str(custom_path))
    with pytest.raises(ValueError, match="unsupported provider"):
        add_custom_model_entry(
            provider="other",
            model_id="x",
            task_type=TASK_TEXT2IMAGE,
            recommended=None,
        )


def test_delete_custom_model_entry_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    custom_path = tmp_path / "custom_models.json"
    monkeypatch.setenv("IGT_CUSTOM_MODELS_PATH", str(custom_path))
    add_custom_model_entry(
        provider="alibaba",
        model_id="my-delete-me",
        task_type=TASK_TEXT2IMAGE,
        recommended=None,
    )
    assert delete_custom_model_entry(
        provider="alibaba",
        model_id="my-delete-me",
        task_type=TASK_TEXT2IMAGE,
    )
    rows = list_model_entries(provider="alibaba", task_type=TASK_TEXT2IMAGE, recommend_only=False)
    assert not any(item["id"] == "my-delete-me" and item["docs"] == "custom" for item in rows)


def test_delete_custom_model_entry_for_builtin_returns_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    custom_path = tmp_path / "custom_models.json"
    monkeypatch.setenv("IGT_CUSTOM_MODELS_PATH", str(custom_path))
    assert not delete_custom_model_entry(
        provider="google",
        model_id="gemini-2.5-flash-image",
        task_type=TASK_TEXT2IMAGE,
    )
