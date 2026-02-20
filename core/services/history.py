import json
from pathlib import Path
from typing import Any, Dict, List, Optional, cast


def list_history_entries(
    output_root: Path, provider: Optional[str], limit: int
) -> List[Dict[str, Any]]:
    if limit <= 0:
        raise ValueError("history list: --limit must be > 0")
    if not output_root.exists():
        return []

    run_dirs = sorted(
        [p for p in output_root.iterdir() if p.is_dir()],
        key=lambda item: item.name,
        reverse=True,
    )
    entries: List[Dict[str, Any]] = []
    for run_dir in run_dirs:
        details = load_history_run_details(run_dir)
        request = cast(Dict[str, Any], details["request"])
        response = cast(Dict[str, Any], details["response"])
        item_provider = cast(str, request.get("provider") or response.get("provider") or "")
        if provider and item_provider != provider:
            continue
        images = response.get("images", [])
        image_count = len(images) if isinstance(images, list) else 0
        entries.append(
            {
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "timestamp": run_dir.name.split("_", 1)[0],
                "provider": item_provider,
                "model": request.get("model") or response.get("model") or "",
                "task_type": request.get("task_type") or response.get("task_type") or "",
                "request_id": response.get("request_id", ""),
                "images": image_count,
                "prompt": _truncate_text(cast(str, request.get("prompt", ""))),
            }
        )
        if len(entries) >= limit:
            break
    return entries


def resolve_history_run_dir(output_root: Path, run_id: str) -> Path:
    candidate = Path(run_id)
    if candidate.exists() and candidate.is_dir():
        return candidate
    run_dir = output_root / run_id
    if run_dir.exists() and run_dir.is_dir():
        return run_dir
    raise ValueError(f"history show: run not found: {run_id}")


def load_history_run_details(run_dir: Path) -> Dict[str, Any]:
    request_path = run_dir / "request.json"
    response_path = run_dir / "response.json"
    saved_images_path = run_dir / "saved_images.json"
    preprocessed_inputs_path = run_dir / "preprocessed_inputs.json"
    if not request_path.exists() or not response_path.exists():
        raise ValueError(f"history: invalid run folder (missing request/response): {run_dir}")
    request_payload = json.loads(request_path.read_text(encoding="utf-8"))
    response_payload = json.loads(response_path.read_text(encoding="utf-8"))
    saved_payload: Dict[str, Any] = {}
    if saved_images_path.exists():
        saved_payload = json.loads(saved_images_path.read_text(encoding="utf-8"))
    preprocessed_payload: Dict[str, Any] = {}
    if preprocessed_inputs_path.exists():
        preprocessed_payload = json.loads(preprocessed_inputs_path.read_text(encoding="utf-8"))
    return {
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "request": request_payload,
        "response": response_payload,
        "saved_images": saved_payload,
        "preprocessed_inputs": preprocessed_payload,
    }


def _truncate_text(value: str, max_len: int = 60) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 3] + "..."
