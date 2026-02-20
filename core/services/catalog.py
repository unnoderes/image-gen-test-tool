import json
import os
from pathlib import Path
from typing import Dict, List, Optional, cast

from core.models import TASK_IMAGE2IMAGE, TASK_TEXT2IMAGE

CATALOG_SNAPSHOT_DATE = "2026-02-19"
MODEL_CATALOG = {
    "alibaba": [
        {
            "id": "qwen-image-max",
            "tasks": [TASK_TEXT2IMAGE],
            "status": "recommended",
            "note": "Qwen image generation",
            "docs": "https://help.aliyun.com/zh/model-studio/models",
        },
        {
            "id": "qwen-image-plus",
            "tasks": [TASK_TEXT2IMAGE],
            "status": "recommended",
            "note": "Lower-cost image generation",
            "docs": "https://help.aliyun.com/zh/model-studio/models",
        },
        {
            "id": "qwen-image",
            "tasks": [TASK_TEXT2IMAGE],
            "status": "available",
            "note": "General image generation",
            "docs": "https://help.aliyun.com/zh/model-studio/models",
        },
        {
            "id": "qwen-image-edit-max",
            "tasks": [TASK_IMAGE2IMAGE],
            "status": "recommended",
            "note": "Best editing quality",
            "docs": "https://help.aliyun.com/zh/model-studio/models",
        },
        {
            "id": "qwen-image-edit-plus",
            "tasks": [TASK_IMAGE2IMAGE],
            "status": "available",
            "note": "Lower-cost editing",
            "docs": "https://help.aliyun.com/zh/model-studio/models",
        },
        {
            "id": "qwen-image-edit",
            "tasks": [TASK_IMAGE2IMAGE],
            "status": "available",
            "note": "Basic editing",
            "docs": "https://help.aliyun.com/zh/model-studio/models",
        },
    ],
    "google": [
        {
            "id": "gemini-2.5-flash-image",
            "tasks": [TASK_TEXT2IMAGE, TASK_IMAGE2IMAGE],
            "status": "recommended",
            "note": "Gemini image generation/editing",
            "docs": "https://ai.google.dev/gemini-api/docs/image-generation",
        }
    ],
    "glm": [
        {
            "id": "cogview-4-250304",
            "tasks": [TASK_TEXT2IMAGE],
            "status": "available",
            "note": "CogView-4 model ID",
            "docs": "https://open.bigmodel.cn/dev/api",
        },
        {
            "id": "glm-image",
            "tasks": [TASK_TEXT2IMAGE],
            "status": "available",
            "note": "GLM image generation",
            "docs": "https://open.bigmodel.cn/dev/api",
        },
    ],
}

CUSTOM_MODELS_ENV = "IGT_CUSTOM_MODELS_PATH"
DEFAULT_CUSTOM_MODELS_FILE = "custom_models.json"
SUPPORTED_PROVIDERS = {"alibaba", "google", "glm"}


def list_model_entries(
    provider: Optional[str], task_type: Optional[str], recommend_only: bool
) -> List[Dict[str, str]]:
    providers = [provider] if provider else ["alibaba", "google", "glm"]
    entries: List[Dict[str, str]] = []
    merged = _merged_catalog()
    for p in providers:
        for item in merged[p]:
            tasks = cast(List[str], item["tasks"])
            if task_type and task_type not in tasks:
                continue
            if recommend_only and item["status"] != "recommended":
                continue
            entries.append(
                {
                    "provider": p,
                    "id": item["id"],
                    "tasks": ",".join(tasks),
                    "status": item["status"],
                    "note": item["note"],
                    "docs": item["docs"],
                }
            )
    return entries


def add_custom_model_entry(
    provider: str,
    model_id: str,
    task_type: str,
    recommended: Optional[bool] = None,
) -> Dict[str, str]:
    provider = provider.strip().lower()
    model_id = model_id.strip()
    task_type = task_type.strip()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"unsupported provider: {provider}")
    if not model_id:
        raise ValueError("model_id is required")
    if task_type not in {TASK_TEXT2IMAGE, TASK_IMAGE2IMAGE}:
        raise ValueError(f"unsupported task_type: {task_type}")

    status = "custom"
    if recommended is True:
        status = "recommended"
    if recommended is False:
        status = "available"
    new_item = {
        "id": model_id,
        "tasks": [task_type],
        "status": status,
        "note": "User custom model",
        "docs": "custom",
    }

    existing = _load_custom_catalog()
    bucket = existing.setdefault(provider, [])
    for item in bucket:
        if item.get("id") == model_id and task_type in cast(List[str], item.get("tasks", [])):
            raise ValueError("custom model already exists for this provider + task_type")
    bucket.append(new_item)
    _save_custom_catalog(existing)
    return {
        "provider": provider,
        "id": model_id,
        "tasks": task_type,
        "status": status,
        "note": "User custom model",
        "docs": "custom",
    }


def delete_custom_model_entry(provider: str, model_id: str, task_type: str) -> bool:
    provider = provider.strip().lower()
    model_id = model_id.strip()
    task_type = task_type.strip()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"unsupported provider: {provider}")
    if not model_id:
        raise ValueError("model_id is required")
    if task_type not in {TASK_TEXT2IMAGE, TASK_IMAGE2IMAGE}:
        raise ValueError(f"unsupported task_type: {task_type}")

    existing = _load_custom_catalog()
    bucket = existing.setdefault(provider, [])
    updated_bucket: List[Dict[str, object]] = []
    deleted = False

    for item in bucket:
        item_id = str(item.get("id", "")).strip()
        tasks = cast(List[str], item.get("tasks", []))
        if item_id != model_id or task_type not in tasks:
            updated_bucket.append(item)
            continue
        deleted = True
        remaining_tasks = [task for task in tasks if task != task_type]
        if remaining_tasks:
            cloned = dict(item)
            cloned["tasks"] = remaining_tasks
            updated_bucket.append(cloned)

    if not deleted:
        return False
    existing[provider] = updated_bucket
    _save_custom_catalog(existing)
    return True


def _merged_catalog() -> Dict[str, List[Dict[str, object]]]:
    merged: Dict[str, List[Dict[str, object]]] = {
        "alibaba": [dict(item) for item in MODEL_CATALOG["alibaba"]],
        "google": [dict(item) for item in MODEL_CATALOG["google"]],
        "glm": [dict(item) for item in MODEL_CATALOG["glm"]],
    }
    custom = _load_custom_catalog()
    for provider, items in custom.items():
        if provider not in merged:
            continue
        for item in items:
            merged[provider].append(dict(item))
    return merged


def _custom_models_path() -> Path:
    value = os.getenv(CUSTOM_MODELS_ENV, "").strip()
    if value:
        path = Path(value).expanduser()
    else:
        path = Path.cwd() / DEFAULT_CUSTOM_MODELS_FILE
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _load_custom_catalog() -> Dict[str, List[Dict[str, object]]]:
    path = _custom_models_path()
    if not path.exists():
        return {provider: [] for provider in SUPPORTED_PROVIDERS}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {provider: [] for provider in SUPPORTED_PROVIDERS}

    catalog: Dict[str, List[Dict[str, object]]] = {provider: [] for provider in SUPPORTED_PROVIDERS}
    if not isinstance(raw, dict):
        return catalog
    for provider, items in raw.items():
        if provider not in SUPPORTED_PROVIDERS or not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id", "")).strip()
            tasks = item.get("tasks", [])
            if not model_id or not isinstance(tasks, list):
                continue
            clean_tasks = [
                task
                for task in tasks
                if task in {TASK_TEXT2IMAGE, TASK_IMAGE2IMAGE}
            ]
            if not clean_tasks:
                continue
            status = str(item.get("status", "custom")).strip() or "custom"
            note = str(item.get("note", "User custom model")).strip() or "User custom model"
            docs = str(item.get("docs", "custom")).strip() or "custom"
            catalog[provider].append(
                {
                    "id": model_id,
                    "tasks": clean_tasks,
                    "status": status,
                    "note": note,
                    "docs": docs,
                }
            )
    return catalog


def _save_custom_catalog(catalog: Dict[str, List[Dict[str, object]]]) -> None:
    path = _custom_models_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        provider: items
        for provider, items in catalog.items()
        if provider in SUPPORTED_PROVIDERS
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
