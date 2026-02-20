import json
from argparse import Namespace
from pathlib import Path

import pytest

from cli import _collect_history_entries, _resolve_run_dir, _run_history


def _write_run(
    root: Path,
    run_id: str,
    provider: str = "alibaba",
    model: str = "qwen-image",
    task_type: str = "text_to_image",
    prompt: str = "A sample prompt",
    image_count: int = 1,
) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    request = {
        "provider": provider,
        "model": model,
        "task_type": task_type,
        "prompt": prompt,
        "input_image": None,
        "size": "1024x1024",
        "n": 1,
        "seed": None,
        "extra": {},
    }
    response = {
        "request_id": "req_x",
        "provider": provider,
        "model": model,
        "task_type": task_type,
        "images": ["x"] * image_count,
        "latency_ms": 100,
        "raw_response": {"ok": True},
    }
    saved = {"saved_files": ["images/image_01.png"]}
    (run_dir / "request.json").write_text(json.dumps(request), encoding="utf-8")
    (run_dir / "response.json").write_text(json.dumps(response), encoding="utf-8")
    (run_dir / "saved_images.json").write_text(json.dumps(saved), encoding="utf-8")
    return run_dir


def test_collect_history_entries_limit_and_sort(tmp_path: Path) -> None:
    _write_run(tmp_path, "20260219-010101_alibaba_text_to_image_req_1")
    _write_run(
        tmp_path,
        "20260219-010102_google_text_to_image_req_2",
        provider="google",
    )
    entries = _collect_history_entries(tmp_path, provider=None, limit=1)
    assert len(entries) == 1
    assert entries[0]["provider"] == "google"


def test_collect_history_entries_provider_filter(tmp_path: Path) -> None:
    _write_run(tmp_path, "20260219-010101_alibaba_text_to_image_req_1", provider="alibaba")
    _write_run(tmp_path, "20260219-010102_google_text_to_image_req_2", provider="google")
    entries = _collect_history_entries(tmp_path, provider="alibaba", limit=10)
    assert len(entries) == 1
    assert entries[0]["provider"] == "alibaba"


def test_collect_history_entries_limit_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="--limit"):
        _collect_history_entries(tmp_path, provider=None, limit=0)


def test_resolve_run_dir_accepts_name_and_path(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path, "20260219-010101_alibaba_text_to_image_req_1")
    by_name = _resolve_run_dir(tmp_path, run_dir.name)
    by_path = _resolve_run_dir(tmp_path, str(run_dir))
    assert by_name == run_dir
    assert by_path == run_dir


def test_run_history_list_json_output(capsys, tmp_path: Path) -> None:
    _write_run(tmp_path, "20260219-010101_alibaba_text_to_image_req_1")
    args = Namespace(
        history_command="list",
        limit=5,
        provider="alibaba",
        format="json",
    )
    _run_history(args, tmp_path)
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_filter"] == "alibaba"
    assert payload["limit"] == 5
    assert len(payload["runs"]) == 1


def test_run_history_show_missing_run_raises(tmp_path: Path) -> None:
    args = Namespace(history_command="show", run_id="not_exist", format="text")
    with pytest.raises(ValueError, match="run not found"):
        _run_history(args, tmp_path)
