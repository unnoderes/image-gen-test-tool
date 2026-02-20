import argparse
import json
import logging
import os
import sys
import threading
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from textwrap import dedent
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, cast

from dotenv import load_dotenv

from core.io_utils import ensure_dir, read_json_file
from core.models import TASK_IMAGE2IMAGE, TASK_TEXT2IMAGE, GenerationRequest
from core.runner import (
    PERSIST_PREPROCESSED_INPUT_ENV,
    cleanup_temp_files,
    persist_run,
    run_with_retry_with_artifacts,
    summarize_results,
)
from core.services import (
    ALIBABA_AUTOCROP_ENV,
    CATALOG_SNAPSHOT_DATE,
    build_adapters_from_env,
    list_history_entries,
    list_model_entries,
    load_history_run_details,
    resolve_history_run_dir,
    resolve_request_size,
)

PACKAGE_NAME = "image-gen-test-tool"
LOGGER = logging.getLogger("image_gen_test_tool")
T = TypeVar("T")


def main() -> int:
    load_dotenv()
    parser = _build_parser()
    args = parser.parse_args()
    _configure_logging(verbose=args.verbose, quiet=args.quiet)
    _apply_cli_env_overrides(args)

    try:
        if args.command == "models":
            _run_models(args)
            return 0

        if args.command == "history":
            _run_history(args, Path(args.output_dir))
            return 0

        adapters = _build_adapters()
        output_root = ensure_dir(Path(args.output_dir))
        max_retries = int(os.getenv("MAX_RETRIES", "1"))
        retry_delay = int(os.getenv("RETRY_DELAY_SECONDS", "2"))

        if args.command == "single":
            request = _request_from_args(args)
            response, preprocessed_inputs = _run_with_progress(
                action=f"generating provider={request.provider} model={request.model}",
                quiet=args.quiet,
                fn=lambda: run_with_retry_with_artifacts(
                    adapter=adapters[request.provider],
                    request=request,
                    max_retries=max_retries,
                    retry_delay_seconds=retry_delay,
                ),
            )
            try:
                run_dir = persist_run(
                    output_root,
                    request,
                    response,
                    preprocessed_inputs=preprocessed_inputs,
                )
            finally:
                cleanup_temp_files(preprocessed_inputs)
            _console_print(
                f"ok provider={request.provider} run_dir={run_dir}",
                quiet=args.quiet,
            )
            return 0

        if args.command == "compare":
            _run_compare(args, adapters, output_root, max_retries, retry_delay)
            return 0

        if args.command == "batch":
            _run_batch(args, adapters, output_root, max_retries, retry_delay)
            return 0

        raise ValueError(f"Unknown command: {args.command}")
    except Exception as exc:  # noqa: BLE001
        _console_error(f"error: {exc}")
        LOGGER.debug("CLI execution failed", exc_info=True)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Minimal image generation API test tool",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=_root_help_epilog(),
    )
    parser.add_argument("--output-dir", default="runs", help="Output root directory")
    parser.add_argument(
        "--auto-crop",
        choices=["on", "off"],
        default=None,
        help="Enable or disable Alibaba image_to_image auto-crop.",
    )
    parser.add_argument(
        "--persist-preprocessed-input",
        choices=["on", "off"],
        default=None,
        help=(
            "Persist Alibaba image_to_image auto-cropped input in each run folder "
            "(preprocessed_inputs/)."
        ),
    )
    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument(
        "--verbose",
        action="store_true",
        help="Show debug logs.",
    )
    verbosity_group.add_argument(
        "--quiet",
        action="store_true",
        help="Only show errors.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_app_version()}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    single = _new_subparser(
        subparsers,
        "single",
        "Run one request",
        _single_help_epilog(),
    )
    _attach_common(single)

    compare = _new_subparser(
        subparsers,
        "compare",
        "Run one prompt on two providers",
        _compare_help_epilog(),
    )
    compare.add_argument("--prompt", required=True)
    compare.add_argument("--task-type", required=True, choices=[TASK_TEXT2IMAGE, TASK_IMAGE2IMAGE])
    compare.add_argument("--provider-a", choices=["alibaba", "google", "glm"])
    compare.add_argument("--model-a")
    compare.add_argument("--provider-b", choices=["alibaba", "google", "glm"])
    compare.add_argument("--model-b")
    compare.add_argument("--model-alibaba")
    compare.add_argument("--model-google")
    compare.add_argument("--input-image", default=None)
    compare.add_argument("--size", default=None)
    compare.add_argument(
        "--negative-prompt-enabled",
        choices=["on", "off"],
        default="off",
        help="Enable or disable negative prompt input (default: off).",
    )
    compare.add_argument("--negative-prompt", default=None)
    compare.add_argument("--n", type=int, default=1)
    compare.add_argument("--seed", type=int, default=None)
    compare.add_argument("--extra-json", default=None)

    batch = _new_subparser(
        subparsers,
        "batch",
        "Run a prompt list on one provider",
        _batch_help_epilog(),
    )
    batch.add_argument("--provider", required=True, choices=["alibaba", "google", "glm"])
    batch.add_argument("--model", required=True)
    batch.add_argument("--task-type", required=True, choices=[TASK_TEXT2IMAGE, TASK_IMAGE2IMAGE])
    batch.add_argument("--prompts-file", required=True, help="One prompt per line")
    batch.add_argument("--input-image", default=None)
    batch.add_argument("--size", default=None)
    batch.add_argument(
        "--negative-prompt-enabled",
        choices=["on", "off"],
        default="off",
        help="Enable or disable negative prompt input (default: off).",
    )
    batch.add_argument("--negative-prompt", default=None)
    batch.add_argument("--n", type=int, default=1)
    batch.add_argument("--seed", type=int, default=None)
    batch.add_argument("--extra-json", default=None)

    models = _new_subparser(
        subparsers,
        "models",
        "Show built-in official model IDs by provider",
        _models_help_epilog(),
    )
    models.add_argument("--provider", choices=["alibaba", "google", "glm"])
    models.add_argument("--task-type", choices=[TASK_TEXT2IMAGE, TASK_IMAGE2IMAGE], default=None)
    models.add_argument(
        "--recommend",
        action="store_true",
        help="Only show models marked as recommended in the built-in catalog.",
    )
    models.add_argument("--format", choices=["text", "json"], default="text")

    history = _new_subparser(
        subparsers,
        "history",
        "Inspect saved generation history under output directory",
        _history_help_epilog(),
    )
    history_subparsers = history.add_subparsers(dest="history_command", required=True)

    history_list = _new_subparser(
        history_subparsers,
        "list",
        "List saved runs",
        _history_list_help_epilog(),
    )
    history_list.add_argument("--limit", type=int, default=20)
    history_list.add_argument("--provider", choices=["alibaba", "google", "glm"])
    history_list.add_argument("--format", choices=["text", "json"], default="text")

    history_show = _new_subparser(
        history_subparsers,
        "show",
        "Show details for one saved run",
        _history_show_help_epilog(),
    )
    history_show.add_argument("--run-id", required=True)
    history_show.add_argument("--format", choices=["text", "json"], default="text")
    return parser


def _new_subparser(subparsers, name: str, help_text: str, epilog: str):
    return subparsers.add_parser(
        name,
        help=help_text,
        description=help_text,
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=epilog,
    )


def _app_version() -> str:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "0.1.0-dev"


def _attach_common(subparser) -> None:
    subparser.add_argument("--provider", required=True, choices=["alibaba", "google", "glm"])
    subparser.add_argument("--model", required=True)
    subparser.add_argument(
        "--task-type",
        required=True,
        choices=[TASK_TEXT2IMAGE, TASK_IMAGE2IMAGE],
    )
    subparser.add_argument("--prompt", required=True)
    subparser.add_argument("--input-image", default=None)
    subparser.add_argument("--size", default=None)
    subparser.add_argument(
        "--negative-prompt-enabled",
        choices=["on", "off"],
        default="off",
        help="Enable or disable negative prompt input (default: off).",
    )
    subparser.add_argument("--negative-prompt", default=None)
    subparser.add_argument("--n", type=int, default=1)
    subparser.add_argument("--seed", type=int, default=None)
    subparser.add_argument("--extra-json", default=None)


def _build_adapters() -> Dict[str, object]:
    return build_adapters_from_env()


def _request_from_args(
    args, provider: str = "", model: str = "", prompt: str = ""
) -> GenerationRequest:
    size = _resolve_request_size(
        task_type=args.task_type,
        supplied_size=args.size,
        input_image=args.input_image,
    )
    negative_prompt_enabled = getattr(args, "negative_prompt_enabled", "off") == "on"
    raw_negative_prompt = cast(Optional[str], getattr(args, "negative_prompt", None))
    negative_prompt: Optional[str] = None
    if negative_prompt_enabled:
        text = (raw_negative_prompt or "").strip()
        if not text:
            raise ValueError(
                "negative_prompt is required when --negative-prompt-enabled is on"
            )
        negative_prompt = text

    return GenerationRequest(
        provider=provider or args.provider,
        model=model or args.model,
        task_type=args.task_type,
        prompt=prompt or args.prompt,
        negative_prompt=negative_prompt,
        input_image=args.input_image,
        size=size,
        n=args.n,
        seed=args.seed,
        extra=read_json_file(args.extra_json),
    )


def _apply_cli_env_overrides(args) -> None:
    auto_crop = getattr(args, "auto_crop", None)
    if auto_crop == "on":
        os.environ[ALIBABA_AUTOCROP_ENV] = "on"
    if auto_crop == "off":
        os.environ[ALIBABA_AUTOCROP_ENV] = "off"

    value = getattr(args, "persist_preprocessed_input", None)
    if value == "on":
        os.environ[PERSIST_PREPROCESSED_INPUT_ENV] = "true"
    if value == "off":
        os.environ[PERSIST_PREPROCESSED_INPUT_ENV] = "false"


def _run_compare(args, adapters, output_root: Path, max_retries: int, retry_delay: int) -> None:
    rows: List[Dict[str, str]] = []
    targets = _resolve_compare_targets(args)
    for provider, model in targets:
        request = _request_from_args(args, provider=provider, model=model, prompt=args.prompt)
        try:
            response, preprocessed_inputs = _run_with_progress(
                action=f"generating provider={provider} model={model}",
                quiet=args.quiet,
                fn=lambda provider=provider, request=request: run_with_retry_with_artifacts(
                    adapter=adapters[provider],
                    request=request,
                    max_retries=max_retries,
                    retry_delay_seconds=retry_delay,
                ),
            )
            try:
                run_dir = persist_run(
                    output_root,
                    request,
                    response,
                    preprocessed_inputs=preprocessed_inputs,
                )
            finally:
                cleanup_temp_files(preprocessed_inputs)
            rows.append(
                {
                    "provider": provider,
                    "model": model,
                    "prompt": request.prompt,
                    "status": "ok",
                    "run_dir": str(run_dir),
                    "error": "",
                }
            )
            _console_print(f"ok provider={provider} run_dir={run_dir}", quiet=args.quiet)
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "provider": provider,
                    "model": model,
                    "prompt": request.prompt,
                    "status": "failed",
                    "run_dir": "",
                    "error": str(exc),
                }
            )
            _console_error(f"failed provider={provider} error={exc}")
    summarize_results(rows, output_root / "compare_summary.csv")
    _console_print(f"summary={output_root / 'compare_summary.csv'}", quiet=args.quiet)


def _run_batch(args, adapters, output_root: Path, max_retries: int, retry_delay: int) -> None:
    prompts = _read_prompts(args.prompts_file)
    rows: List[Dict[str, str]] = []
    total = len(prompts)
    for index, prompt in enumerate(prompts, start=1):
        request = _request_from_args(args, prompt=prompt)
        try:
            response, preprocessed_inputs = _run_with_progress(
                action=(
                    f"batch {index}/{total} provider={request.provider} "
                    f"model={request.model}"
                ),
                quiet=args.quiet,
                fn=lambda request=request: run_with_retry_with_artifacts(
                    adapter=adapters[request.provider],
                    request=request,
                    max_retries=max_retries,
                    retry_delay_seconds=retry_delay,
                ),
            )
            try:
                run_dir = persist_run(
                    output_root,
                    request,
                    response,
                    preprocessed_inputs=preprocessed_inputs,
                )
            finally:
                cleanup_temp_files(preprocessed_inputs)
            rows.append(
                {
                    "provider": request.provider,
                    "model": request.model,
                    "prompt": request.prompt,
                    "status": "ok",
                    "run_dir": str(run_dir),
                    "error": "",
                }
            )
            _console_print(f"ok prompt={prompt[:40]} run_dir={run_dir}", quiet=args.quiet)
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "provider": request.provider,
                    "model": request.model,
                    "prompt": request.prompt,
                    "status": "failed",
                    "run_dir": "",
                    "error": str(exc),
                }
            )
            _console_error(f"failed prompt={prompt[:40]} error={exc}")
    summarize_results(rows, output_root / "batch_summary.csv")
    _console_print(f"summary={output_root / 'batch_summary.csv'}", quiet=args.quiet)


def _read_prompts(path: str) -> List[str]:
    items = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s:
            items.append(s)
    if not items:
        raise ValueError("prompts file is empty")
    return items


def _collect_model_entries(
    provider: Optional[str], task_type: Optional[str], recommend_only: bool
) -> List[Dict[str, str]]:
    return list_model_entries(provider, task_type, recommend_only)


def _run_models(args) -> None:
    entries = _collect_model_entries(args.provider, args.task_type, args.recommend)
    if args.format == "json":
        payload = {
            "snapshot_date": CATALOG_SNAPSHOT_DATE,
            "provider_filter": args.provider,
            "task_type_filter": args.task_type,
            "recommend_filter": args.recommend,
            "models": entries,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    _print_models_text(entries)


def _run_history(args, output_root: Path) -> None:
    if args.history_command == "list":
        entries = _collect_history_entries(
            output_root=output_root,
            provider=args.provider,
            limit=args.limit,
        )
        if args.format == "json":
            payload = {
                "output_dir": str(output_root),
                "provider_filter": args.provider,
                "limit": args.limit,
                "runs": entries,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        _print_history_list(entries, output_root)
        return

    if args.history_command == "show":
        run_dir = _resolve_run_dir(output_root, args.run_id)
        details = _load_run_details(run_dir)
        if args.format == "json":
            print(json.dumps(details, ensure_ascii=False, indent=2))
            return
        _print_history_show(details)
        return

    raise ValueError(f"Unknown history command: {args.history_command}")


def _print_models_text(entries: List[Dict[str, str]]) -> None:
    if not entries:
        print("No models found.")
        return
    print(
        f"Built-in official model IDs (curated snapshot: {CATALOG_SNAPSHOT_DATE}, "
        "update as providers evolve):"
    )
    print("")
    headers = ("provider", "model_id", "tasks", "status", "note")
    print(
        f"{headers[0]:<10} {headers[1]:<30} {headers[2]:<30} {headers[3]:<12} {headers[4]}"
    )
    print("-" * 130)
    for row in entries:
        print(
            f"{row['provider']:<10} {row['id']:<30} {row['tasks']:<30} "
            f"{row['status']:<12} {row['note']}"
        )
        print(f"{'':<10} docs: {row['docs']}")


def _collect_history_entries(
    output_root: Path, provider: Optional[str], limit: int
) -> List[Dict[str, Any]]:
    return list_history_entries(output_root, provider, limit)


def _print_history_list(entries: List[Dict[str, Any]], output_root: Path) -> None:
    if not entries:
        print(f"No saved runs found under {output_root}")
        return
    print(f"Saved runs under {output_root}:")
    print("")
    headers = ("run_id", "provider", "model", "task_type", "images")
    print(
        f"{headers[0]:<42} {headers[1]:<10} {headers[2]:<28} {headers[3]:<15} {headers[4]}"
    )
    print("-" * 115)
    for row in entries:
        print(
            f"{row['run_id']:<42} {row['provider']:<10} {row['model']:<28} "
            f"{row['task_type']:<15} {row['images']}"
        )


def _resolve_run_dir(output_root: Path, run_id: str) -> Path:
    return resolve_history_run_dir(output_root, run_id)


def _load_run_details(run_dir: Path) -> Dict[str, Any]:
    return load_history_run_details(run_dir)


def _print_history_show(details: Dict[str, Any]) -> None:
    print(f"run_id: {details['run_id']}")
    print(f"run_dir: {details['run_dir']}")
    print("")
    print("request:")
    print(json.dumps(details["request"], ensure_ascii=False, indent=2))
    print("")
    print("response:")
    print(json.dumps(details["response"], ensure_ascii=False, indent=2))
    if details["saved_images"]:
        print("")
        print("saved_images:")
        print(json.dumps(details["saved_images"], ensure_ascii=False, indent=2))
    if details.get("preprocessed_inputs"):
        print("")
        print("preprocessed_inputs:")
        print(json.dumps(details["preprocessed_inputs"], ensure_ascii=False, indent=2))


def _resolve_request_size(
    task_type: str, supplied_size: Optional[str], input_image: Optional[str]
) -> Optional[str]:
    return resolve_request_size(task_type, supplied_size, input_image)


def _resolve_compare_targets(args) -> List[Tuple[str, str]]:
    has_new_provider_a = bool(args.provider_a)
    has_new_provider_b = bool(args.provider_b)
    has_new_model_a = bool(args.model_a)
    has_new_model_b = bool(args.model_b)
    has_any_new = has_new_provider_a or has_new_provider_b or has_new_model_a or has_new_model_b
    has_new_full = has_new_provider_a and has_new_provider_b and has_new_model_a and has_new_model_b

    has_old_a = bool(args.model_alibaba)
    has_old_b = bool(args.model_google)
    has_any_old = has_old_a or has_old_b
    has_old_full = has_old_a and has_old_b

    if has_any_new and has_any_old:
        raise ValueError(
            "compare: use either (--provider-a/--model-a/--provider-b/--model-b) "
            "or (--model-alibaba/--model-google), not both."
        )

    if has_new_full:
        return [(args.provider_a, args.model_a), (args.provider_b, args.model_b)]

    if has_any_new and not has_new_full:
        raise ValueError(
            "compare: missing args. new mode requires "
            "--provider-a --model-a --provider-b --model-b."
        )

    if has_old_full:
        return [("alibaba", args.model_alibaba), ("google", args.model_google)]

    if has_any_old and not has_old_full:
        raise ValueError("compare: legacy mode requires both --model-alibaba and --model-google.")

    raise ValueError(
        "compare: specify providers/models using new mode "
        "(--provider-a --model-a --provider-b --model-b)."
    )


def _root_help_epilog() -> str:
    return dedent(
        """\
        Quick Examples:
          1) Single text-to-image:
             igt single --provider alibaba --model qwen-image
               --task-type text_to_image --prompt "A mountain at sunrise"

          2) Compare Alibaba vs Google:
             igt compare --prompt "A red sports car" --task-type text_to_image
               --provider-a alibaba --model-a qwen-image
               --provider-b google --model-b gemini-2.5-flash-image

          3) Batch prompts from file:
             igt batch --provider alibaba --model qwen-image
               --task-type text_to_image --prompts-file prompts.txt

          4) Single text-to-image with GLM:
             igt single --provider glm --model cogview-4-250304
               --task-type text_to_image --prompt "A cyberpunk city at night"

          5) Show built-in model IDs:
             igt models
             igt models --provider alibaba
             igt models --recommend
             igt models --provider alibaba --task-type image_to_image
             igt models --format json

          6) Inspect generation history:
             igt history list --limit 10
             igt history show --run-id 20260219-120301_alibaba_text_to_image_req_abc

        Tips:
          - Use '--verbose' to print debug logs.
          - Use '--quiet' to suppress normal output.
          - Negative prompt is OFF by default; use '--negative-prompt-enabled on'.
          - Alibaba image_to_image auto-crop is OFF by default.
          - Use '--auto-crop on' to enable Alibaba image_to_image auto-crop.
          - Use '--persist-preprocessed-input on' to save auto-cropped input files per run.
          - Run 'igt <command> --help' for command-specific examples.
        """
    )


def _single_help_epilog() -> str:
    return dedent(
        """\
        Examples:
          Text-to-image:
            igt single --provider alibaba --model qwen-image
              --task-type text_to_image --prompt "A cozy cabin in snow"
              --size 1024x1024 --n 1

          Image-to-image:
            igt single --provider google --model gemini-2.5-flash-image
              --task-type image_to_image --prompt "Turn into anime style"
              --input-image "C:\\path\\input.png"

        Notes:
          - '--input-image' is required when task-type is image_to_image.
          - If '--size' is omitted for image_to_image, the tool auto-uses source image size.
          - Use '--negative-prompt-enabled on --negative-prompt \"...\"' to pass negative prompt.
          - Alibaba image_to_image auto-crop is OFF by default.
          - Use '--auto-crop on' to enable center-crop/resize into [512, 2048].
          - '--extra-json extra.json' can pass provider-specific fields.
        """
    )


def _compare_help_epilog() -> str:
    return dedent(
        """\
        New mode (recommended):
          igt compare --prompt "A red sports car drifting on wet road"
            --task-type text_to_image
            --provider-a alibaba --model-a qwen-image
            --provider-b glm --model-b cogview-4-250304

        Legacy mode (compatible):
          igt compare --prompt "A red sports car drifting on wet road"
            --task-type text_to_image
            --model-alibaba qwen-image
            --model-google gemini-2.5-flash-image

        Output:
          - Saves each run under runs/{timestamp}_...
          - Writes compare_summary.csv in --output-dir.
        """
    )


def _batch_help_epilog() -> str:
    return dedent(
        """\
        Example:
          igt batch --provider alibaba --model qwen-image
            --task-type text_to_image --prompts-file prompts.txt

        prompts.txt format:
          One prompt per line. Empty lines are ignored.
        """
    )


def _models_help_epilog() -> str:
    return dedent(
        """\
        Examples:
          igt models
          igt models --provider alibaba
          igt models --recommend
          igt models --task-type image_to_image
          igt models --provider glm --format json

        Notes:
          - This list is curated and hardcoded for quick lookup in CLI.
          - Add '--recommend' to keep only recommended models.
          - Add '--task-type' to narrow to callable models for that task.
          - Use provider docs to verify latest released snapshots.
        """
    )


def _history_help_epilog() -> str:
    return dedent(
        """\
        Examples:
          igt history list
          igt history list --provider alibaba --limit 10
          igt history show --run-id 20260219-120301_alibaba_text_to_image_req_abc

        Notes:
          - Reads saved runs from '--output-dir' (default: runs).
          - 'show --run-id' accepts folder name or absolute folder path.
        """
    )


def _history_list_help_epilog() -> str:
    return dedent(
        """\
        Examples:
          igt history list
          igt history list --limit 5
          igt history list --provider google --format json
        """
    )


def _history_show_help_epilog() -> str:
    return dedent(
        """\
        Examples:
          igt history show --run-id 20260219-120301_alibaba_text_to_image_req_abc
          igt history show --run-id runs\\20260219-120301_alibaba_text_to_image_req_abc
          igt history show --run-id 20260219-120301_alibaba_text_to_image_req_abc --format json
        """
    )


def _configure_logging(verbose: bool, quiet: bool) -> None:
    level = logging.INFO
    if verbose:
        level = logging.DEBUG
    if quiet:
        level = logging.ERROR
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def _console_print(message: str, quiet: bool) -> None:
    if quiet:
        return
    print(message)


def _console_error(message: str) -> None:
    print(message, file=sys.stderr)


def _run_with_progress(action: str, quiet: bool, fn: Callable[[], T]) -> T:
    if quiet:
        return fn()

    state: Dict[str, object] = {"result": None, "error": None}

    def _target() -> None:
        try:
            state["result"] = fn()
        except Exception as exc:  # noqa: BLE001
            state["error"] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()

    spinner = "|/-\\"
    spin_idx = 0
    started = time.monotonic()
    while thread.is_alive():
        elapsed = int(time.monotonic() - started)
        sys.stdout.write(f"\r[waiting {spinner[spin_idx % len(spinner)]}] {action} ... {elapsed}s")
        sys.stdout.flush()
        spin_idx += 1
        thread.join(0.2)

    # Clear spinner line.
    sys.stdout.write("\r" + (" " * 120) + "\r")
    sys.stdout.flush()

    error = state["error"]
    if error is not None:
        raise cast(Exception, error)

    elapsed = int(time.monotonic() - started)
    _console_print(f"done in {elapsed}s: {action}", quiet=False)
    return cast(T, state["result"])


if __name__ == "__main__":
    raise SystemExit(main())
