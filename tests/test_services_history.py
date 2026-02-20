import json
from pathlib import Path

import pytest

from core.services.history import (
    list_history_entries,
    load_history_run_details,
    resolve_history_run_dir,
)


def _write_run(root: Path, run_id: str, provider: str = "alibaba") -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    request = {
        "provider": provider,
        "model": "qwen-image",
        "task_type": "text_to_image",
        "prompt": "A sample prompt",
    }
    response = {
        "request_id": "req_x",
        "provider": provider,
        "model": "qwen-image",
        "task_type": "text_to_image",
        "images": ["x"],
        "latency_ms": 100,
        "raw_response": {"ok": True},
    }
    (run_dir / "request.json").write_text(json.dumps(request), encoding="utf-8")
    (run_dir / "response.json").write_text(json.dumps(response), encoding="utf-8")
    return run_dir


def test_list_history_entries_filters_and_limits(tmp_path: Path) -> None:
    _write_run(tmp_path, "20260219-010101_alibaba_text_to_image_req_1", provider="alibaba")
    _write_run(tmp_path, "20260219-010102_google_text_to_image_req_2", provider="google")
    entries = list_history_entries(tmp_path, provider="google", limit=1)
    assert len(entries) == 1
    assert entries[0]["provider"] == "google"


def test_resolve_history_run_dir_and_load_details(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path, "20260219-010101_alibaba_text_to_image_req_1")
    assert resolve_history_run_dir(tmp_path, run_dir.name) == run_dir
    details = load_history_run_details(run_dir)
    assert details["run_id"] == run_dir.name
    assert details["request"]["provider"] == "alibaba"


def test_resolve_history_run_dir_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="run not found"):
        resolve_history_run_dir(tmp_path, "missing")
