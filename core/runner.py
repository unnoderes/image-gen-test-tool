import base64
import os
import time
from pathlib import Path
from typing import Dict, List, Protocol, Tuple

import requests

from core.io_utils import ensure_dir, json_dump
from core.models import GenerationRequest, GenerationResponse
from core.services.generation import prepare_request_for_execution

PERSIST_PREPROCESSED_INPUT_ENV = "IGT_PERSIST_PREPROCESSED_INPUT"


class GenerationAdapter(Protocol):
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        ...


def run_with_retry(
    adapter: GenerationAdapter,
    request: GenerationRequest,
    max_retries: int,
    retry_delay_seconds: int,
) -> GenerationResponse:
    response, cleanup_paths = run_with_retry_with_artifacts(
        adapter=adapter,
        request=request,
        max_retries=max_retries,
        retry_delay_seconds=retry_delay_seconds,
    )
    cleanup_temp_files(cleanup_paths)
    return response


def run_with_retry_with_artifacts(
    adapter: GenerationAdapter,
    request: GenerationRequest,
    max_retries: int,
    retry_delay_seconds: int,
) -> Tuple[GenerationResponse, List[Path]]:
    prepared_request, cleanup_paths = prepare_request_for_execution(request)
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return adapter.generate(prepared_request), cleanup_paths
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == max_retries:
                break
            time.sleep(retry_delay_seconds)
    raise RuntimeError(f"Request failed after retries: {last_error}") from last_error


def persist_run(
    output_root: Path,
    request: GenerationRequest,
    response: GenerationResponse,
    preprocessed_inputs: List[Path] | None = None,
) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = ensure_dir(
        output_root / f"{timestamp}_{request.provider}_{request.task_type}_{response.request_id}"
    )
    json_dump(run_dir / "request.json", request.to_dict())
    json_dump(run_dir / "response.json", response.to_dict())
    saved = save_images(run_dir, response.images)
    json_dump(run_dir / "saved_images.json", {"saved_files": saved})
    if preprocessed_inputs and should_persist_preprocessed_inputs():
        saved_preprocessed = save_preprocessed_inputs(run_dir, preprocessed_inputs)
        if saved_preprocessed:
            json_dump(
                run_dir / "preprocessed_inputs.json",
                {"saved_files": saved_preprocessed},
            )
    return run_dir


def save_images(run_dir: Path, images: List[str]) -> List[str]:
    saved_files: List[str] = []
    images_dir = ensure_dir(run_dir / "images")
    for index, item in enumerate(images, start=1):
        filename = f"image_{index:02d}"
        if item.startswith("http://") or item.startswith("https://"):
            target = images_dir / f"{filename}.bin"
            try:
                resp = requests.get(item, timeout=60)
                resp.raise_for_status()
                with open(target, "wb") as f:
                    f.write(resp.content)
                saved_files.append(str(target))
                alias = _write_bin_alias_file(target, resp.content)
                if alias:
                    saved_files.append(str(alias))
            except Exception:  # noqa: BLE001
                txt_target = images_dir / f"{filename}.url.txt"
                txt_target.write_text(item, encoding="utf-8")
                saved_files.append(str(txt_target))
            continue

        if item.startswith("data:image/"):
            header, b64 = item.split(",", 1)
            ext = _ext_from_data_uri_header(header)
            target = images_dir / f"{filename}.{ext}"
            _write_base64_image(target, b64)
            saved_files.append(str(target))
            continue

        # Try raw base64 as a fallback.
        try:
            target = images_dir / f"{filename}.png"
            _write_base64_image(target, item)
            saved_files.append(str(target))
        except Exception:  # noqa: BLE001
            txt_target = images_dir / f"{filename}.txt"
            txt_target.write_text(item, encoding="utf-8")
            saved_files.append(str(txt_target))
    return saved_files


def _write_base64_image(path: Path, b64_payload: str) -> None:
    with open(path, "wb") as f:
        f.write(base64.b64decode(b64_payload))


def _ext_from_data_uri_header(header: str) -> str:
    # Example header: data:image/png;base64
    if "image/" not in header:
        return "png"
    mime = header.split(":", 1)[1].split(";", 1)[0]
    subtype = mime.split("/", 1)[1]
    return subtype or "png"


def _write_bin_alias_file(bin_path: Path, content: bytes) -> Path | None:
    ext = _resolve_bin_alias_ext()
    if not ext:
        return None
    alias_path = bin_path.with_suffix(f".{ext}")
    with open(alias_path, "wb") as f:
        f.write(content)
    return alias_path


def _resolve_bin_alias_ext() -> str | None:
    raw = os.getenv("IGT_BIN_ALIAS_FORMAT", "png").strip().lower()
    if raw in {"off", "none", "disable", "disabled", ""}:
        return None
    if raw in {"jpg", "jpeg"}:
        return "jpg"
    if raw == "png":
        return "png"
    return "png"


def should_persist_preprocessed_inputs() -> bool:
    raw = os.getenv(PERSIST_PREPROCESSED_INPUT_ENV, "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def save_preprocessed_inputs(run_dir: Path, preprocessed_inputs: List[Path]) -> List[str]:
    saved_files: List[str] = []
    target_dir = ensure_dir(run_dir / "preprocessed_inputs")
    for index, source in enumerate(preprocessed_inputs, start=1):
        if not source.exists() or not source.is_file():
            continue
        suffix = source.suffix.lower() or ".png"
        target = target_dir / f"input_{index:02d}{suffix}"
        target.write_bytes(source.read_bytes())
        saved_files.append(str(target))
    return saved_files


def cleanup_temp_files(paths: List[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            continue


def summarize_results(results: List[Dict[str, str]], output_path: Path) -> None:
    lines = ["provider,model,prompt,status,run_dir,error"]
    for row in results:
        line = ",".join(
            [
                _escape_csv(row.get("provider", "")),
                _escape_csv(row.get("model", "")),
                _escape_csv(row.get("prompt", "")),
                _escape_csv(row.get("status", "")),
                _escape_csv(row.get("run_dir", "")),
                _escape_csv(row.get("error", "")),
            ]
        )
        lines.append(line)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _escape_csv(value: str) -> str:
    if "," in value or '"' in value or "\n" in value:
        return '"' + value.replace('"', '""') + '"'
    return value
