from core.models import TASK_IMAGE2IMAGE
from core.services.catalog import list_model_entries


def test_list_model_entries_returns_multi_provider_rows() -> None:
    entries = list_model_entries(provider=None, task_type=None, recommend_only=False)
    assert entries
    assert any(item["provider"] == "alibaba" for item in entries)
    assert any(item["provider"] == "google" for item in entries)
    assert any(item["provider"] == "glm" for item in entries)


def test_list_model_entries_supports_combined_filters() -> None:
    entries = list_model_entries(
        provider="google",
        task_type=TASK_IMAGE2IMAGE,
        recommend_only=True,
    )
    assert entries
    assert all(item["provider"] == "google" for item in entries)
    assert all(item["status"] == "recommended" for item in entries)
