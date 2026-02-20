import json
from argparse import Namespace

from cli import _collect_model_entries, _run_models
from core.models import TASK_IMAGE2IMAGE


def test_collect_model_entries_without_filters() -> None:
    entries = _collect_model_entries(provider=None, task_type=None, recommend_only=False)
    assert entries
    assert any(item["provider"] == "alibaba" for item in entries)
    assert any(item["provider"] == "google" for item in entries)
    assert any(item["provider"] == "glm" for item in entries)
    assert all("status" in item and "docs" in item for item in entries)


def test_collect_model_entries_filters_by_provider_and_task_type() -> None:
    entries = _collect_model_entries(
        provider="alibaba",
        task_type=TASK_IMAGE2IMAGE,
        recommend_only=False,
    )
    assert entries
    assert all(item["provider"] == "alibaba" for item in entries)
    assert all(TASK_IMAGE2IMAGE in item["tasks"].split(",") for item in entries)


def test_collect_model_entries_recommend_only() -> None:
    entries = _collect_model_entries(provider=None, task_type=None, recommend_only=True)
    assert entries
    assert all(item["status"] == "recommended" for item in entries)


def test_run_models_json_output_shape(capsys) -> None:
    args = Namespace(
        provider="google",
        task_type=TASK_IMAGE2IMAGE,
        recommend=True,
        format="json",
    )
    _run_models(args)
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_filter"] == "google"
    assert payload["task_type_filter"] == TASK_IMAGE2IMAGE
    assert payload["recommend_filter"] is True
    assert isinstance(payload["models"], list)
    assert payload["models"]
