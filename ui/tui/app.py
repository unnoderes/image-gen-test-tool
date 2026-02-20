import asyncio
import base64
import contextlib
import importlib.util
import json
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, cast
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv, set_key
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.events import Key, Resize
from textual.message import Message
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Pretty,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from core.io_utils import ensure_dir, parse_input_image, read_json_file
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
    add_custom_model_entry,
    delete_custom_model_entry,
    is_alibaba_autocrop_enabled,
    list_history_entries,
    list_model_entries,
    load_history_run_details,
    resolve_request_size,
)
from core.services.generation import build_adapters_from_env

RUN_MODE_SINGLE = "single"
RUN_MODE_COMPARE = "compare"
RUN_MODE_BATCH = "batch"
OUTPUT_DIR_ENV = "IGT_OUTPUT_DIR"
BIN_ALIAS_FORMAT_ENV = "IGT_BIN_ALIAS_FORMAT"
PERSIST_PREPROCESSED_INPUT_DEFAULT = "off"
AUTOCROP_DEFAULT = "off"
DEFAULT_SIZE_DIMENSION = "1024"
VIDEO_TASK_TEXT2VIDEO = "text_to_video"
VIDEO_TASK_IMAGE2VIDEO = "image_to_video"
ALIBABA_VIDEO_DEFAULT_MODEL = "wan2.6-i2v-flash"
ALIBABA_VIDEO_DEFAULT_DURATION = "5"
ALIBABA_VIDEO_DEFAULT_RESOLUTION = "720P"
ALIBABA_VIDEO_PATH = "/api/v1/services/aigc/video-generation/video-synthesis"
ALIBABA_VIDEO_TASKS_PATH = "/api/v1/tasks"
ALIBABA_VIDEO_HOSTS = {
    "intl": "https://dashscope-intl.aliyuncs.com",
    "cn": "https://dashscope.aliyuncs.com",
}
SPEECH_TASK_TEXT2SPEECH = "text_to_speech"
ALIBABA_SPEECH_DEFAULT_MODEL = "qwen3-tts-vd-realtime-2026-01-15"
ALIBABA_SPEECH_MODE_SERVER_COMMIT = "server_commit"
ALIBABA_SPEECH_MODE_COMMIT = "commit"
ALIBABA_SPEECH_AUDIO_FORMAT = "pcm_24000hz_mono_16bit"
ALIBABA_SPEECH_WS_HOSTS = {
    "intl": "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
    "cn": "wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
}
WAN26_IMAGE_MIN_PIXELS = 589_824
WAN26_IMAGE_MAX_PIXELS = 1_638_400
SIZE_GROUP_ALL = "all"
SIZE_GROUP_SQUARE = "square"
SIZE_GROUP_LANDSCAPE = "landscape"
SIZE_GROUP_PORTRAIT = "portrait"
SIZE_DIMENSION_CHOICES = [
    512,
    640,
    768,
    832,
    896,
    960,
    1024,
    1152,
    1280,
    1344,
    1536,
    1792,
    2048,
]
SELECT_ALL = "__all__"
SELECT_UNSET = "__unset__"
SELECT_NONE_MODEL = "__none_model__"
PROVIDER_API_KEY_ENV = {
    "alibaba": "ALIBABA_API_KEY",
    "google": "GOOGLE_API_KEY",
    "glm": "GLM_API_KEY",
}
API_KEY_FIELDS = [
    ("ALIBABA_API_KEY", "conf-alibaba-key"),
    ("GOOGLE_API_KEY", "conf-google-key"),
    ("GLM_API_KEY", "conf-glm-key"),
]


class PromptTextArea(TextArea):
    class Submit(Message):
        def __init__(self, sender: "PromptTextArea") -> None:
            super().__init__()
            self.sender = sender

    def on_key(self, event: Key) -> None:
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self.post_message(self.Submit(self))
            return
        if event.key in {"ctrl+j", "ctrl+enter"}:
            event.prevent_default()
            event.stop()
            self.insert("\n")


class ImageGenTuiApp(App[None]):
    BINDINGS = [
        Binding("ctrl+c", "copy_focus", "Copy", show=True),
    ]

    CSS = """
    Screen {
        layout: vertical;
    }

    TabbedContent {
        height: 1fr;
    }

    .section {
        padding: 1;
    }

    .form-row {
        height: auto;
        margin-bottom: 1;
    }

    .form-row > * {
        width: 1fr;
        margin-right: 1;
    }

    .full {
        width: 1fr;
    }

    #generate-status {
        height: 6;
        content-align: left middle;
        border: solid $primary;
        padding: 0 1;
    }

    #gen-spacer {
        height: 1fr;
    }

    #gen-prompt-hint {
        height: auto;
        color: $text-muted;
        padding: 0 1;
    }

    #gen-size-hint {
        height: auto;
        color: $text-muted;
        padding: 0 1;
    }

    #gen-guide {
        height: auto;
        color: $text-muted;
        border: solid $surface;
        padding: 0 1;
    }

    #gen-guide.guide-error {
        border: solid $error;
        color: $text;
    }

    #gen-guide.guide-warn {
        border: solid $warning;
        color: $text;
    }

    #gen-guide.guide-ready {
        border: solid $success;
        color: $text;
    }

    #gen-prompt {
        min-height: 3;
        border: solid $accent;
    }

    #video-prompt {
        min-height: 3;
        border: solid $accent;
    }

    #video-spacer {
        height: 1fr;
    }

    #video-prompt-hint {
        height: auto;
        color: $text-muted;
        padding: 0 1;
    }

    #speech-prompt {
        min-height: 3;
        border: solid $accent;
    }

    #speech-spacer {
        height: 1fr;
    }

    #speech-prompt-hint {
        height: auto;
        color: $text-muted;
        padding: 0 1;
    }

    #models-hint, #history-hint, #config-hint {
        height: auto;
        color: $text-muted;
        padding: 0 1;
    }

    #models-status {
        height: 3;
        border: solid $primary;
        padding: 0 1;
        content-align: left middle;
    }

    #models-table, #history-table {
        height: 1fr;
    }

    #history-detail {
        height: 12;
        border: solid $accent;
    }

    #config-status {
        height: 3;
        border: solid $primary;
        padding: 0 1;
        content-align: left middle;
    }

    #video-status {
        height: 6;
        border: solid $primary;
        padding: 0 1;
        content-align: left middle;
    }

    #speech-status {
        height: 6;
        border: solid $primary;
        padding: 0 1;
        content-align: left middle;
    }

    #video-guide {
        height: auto;
        color: $text-muted;
        border: solid $surface;
        padding: 0 1;
    }

    #speech-guide {
        height: auto;
        color: $text-muted;
        border: solid $surface;
        padding: 0 1;
    }

    #config-guide {
        height: auto;
        color: $text-muted;
        border: solid $surface;
        padding: 0 1;
    }

    #config-guide.guide-error {
        border: solid $error;
        color: $text;
    }

    #config-guide.guide-warn {
        border: solid $warning;
        color: $text;
    }

    #config-guide.guide-ready {
        border: solid $success;
        color: $text;
    }

    #video-guide.guide-error {
        border: solid $error;
        color: $text;
    }

    #video-guide.guide-warn {
        border: solid $warning;
        color: $text;
    }

    #video-guide.guide-ready {
        border: solid $success;
        color: $text;
    }

    #speech-guide.guide-error {
        border: solid $error;
        color: $text;
    }

    #speech-guide.guide-warn {
        border: solid $warning;
        color: $text;
    }

    #speech-guide.guide-ready {
        border: solid $success;
        color: $text;
    }
    """

    def __init__(self, output_dir: str = "runs") -> None:
        super().__init__()
        self.output_root = self._resolve_output_dir(output_dir)
        self._last_history_detail: Dict[str, Any] = {}
        self._last_models_entries: List[Dict[str, str]] = []
        self._generate_task: Optional[asyncio.Task[None]] = None
        self._generate_watch_task: Optional[asyncio.Task[None]] = None
        self._generate_progress_task: Optional[asyncio.Task[None]] = None
        self._generate_started_at: float = 0.0
        self._generate_latest_log: str = ""
        self._generate_log_handler: Optional[logging.Handler] = None
        self._generate_log_prev_level: Optional[int] = None
        self._video_task: Optional[asyncio.Task[None]] = None
        self._video_watch_task: Optional[asyncio.Task[None]] = None
        self._video_progress_task: Optional[asyncio.Task[None]] = None
        self._video_started_at: float = 0.0
        self._speech_task: Optional[asyncio.Task[None]] = None
        self._speech_watch_task: Optional[asyncio.Task[None]] = None
        self._speech_progress_task: Optional[asyncio.Task[None]] = None
        self._speech_started_at: float = 0.0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent():
            with TabPane("Generate", id="tab-generate"):
                with VerticalScroll(classes="section"):
                    with Horizontal(classes="form-row", id="gen-row-core"):
                        yield Select(
                            options=[
                                ("single", RUN_MODE_SINGLE),
                                ("compare", RUN_MODE_COMPARE),
                                ("batch", RUN_MODE_BATCH),
                            ],
                            value=RUN_MODE_SINGLE,
                            id="gen-mode",
                        )
                        yield Select(
                            options=[
                                ("Alibaba", "alibaba"),
                                ("Google", "google"),
                                ("GLM", "glm"),
                            ],
                            value="alibaba",
                            id="gen-provider",
                        )
                        yield Select(
                            options=[("No available model", SELECT_NONE_MODEL)],
                            value=SELECT_NONE_MODEL,
                            id="gen-model",
                        )
                        yield Select(
                            options=[
                                ("text_to_image", TASK_TEXT2IMAGE),
                                ("image_to_image", TASK_IMAGE2IMAGE),
                            ],
                            value=TASK_TEXT2IMAGE,
                            id="gen-task",
                        )
                    with Horizontal(classes="form-row", id="gen-row-compare"):
                        yield Select(
                            options=[
                                ("Alibaba", "alibaba"),
                                ("Google", "google"),
                                ("GLM", "glm"),
                            ],
                            value="alibaba",
                            id="gen-provider-b",
                        )
                        yield Select(
                            options=[("No available model", SELECT_NONE_MODEL)],
                            value=SELECT_NONE_MODEL,
                            id="gen-model-b",
                        )
                    with Horizontal(classes="form-row", id="gen-row-batch"):
                        yield Input(
                            placeholder="Prompts file (batch mode)",
                            id="gen-prompts-file",
                            classes="full",
                        )
                    with Horizontal(classes="form-row", id="gen-row-image"):
                        yield Input(
                            placeholder=(
                                "Input image path / URL "
                                "(image_to_image; Alibaba auto-crop optional)"
                            ),
                            id="gen-input-image",
                        )
                        yield Select(
                            options=[
                                ("All", SIZE_GROUP_ALL),
                                ("Square", SIZE_GROUP_SQUARE),
                                ("Landscape", SIZE_GROUP_LANDSCAPE),
                                ("Portrait", SIZE_GROUP_PORTRAIT),
                            ],
                            value=SIZE_GROUP_ALL,
                            id="gen-size-group",
                        )
                        yield Select(
                            options=[(DEFAULT_SIZE_DIMENSION, DEFAULT_SIZE_DIMENSION)],
                            value=DEFAULT_SIZE_DIMENSION,
                            id="gen-width",
                        )
                        yield Select(
                            options=[(DEFAULT_SIZE_DIMENSION, DEFAULT_SIZE_DIMENSION)],
                            value=DEFAULT_SIZE_DIMENSION,
                            id="gen-height",
                        )
                        yield Input(placeholder="n (default 1)", value="1", id="gen-n")
                    with Horizontal(classes="form-row", id="gen-row-negative"):
                        yield Select(
                            options=[
                                ("negative prompt: off", "off"),
                                ("negative prompt: on", "on"),
                            ],
                            value="off",
                            id="gen-negative-enabled",
                        )
                        yield Input(
                            placeholder="Negative prompt (enabled only when switch is on)",
                            id="gen-negative-prompt",
                            classes="full",
                        )
                    yield Static("Selected size: 1024x1024", id="gen-size-hint")
                    yield Static("", id="gen-guide")
                    with Horizontal(classes="form-row"):
                        yield Input(
                            placeholder="Extra JSON path (optional)",
                            id="gen-extra-json",
                            classes="full",
                        )
                    yield Static("Ready.", id="generate-status")
                    yield Static("", id="gen-spacer")
                    yield Static(
                        "Prompt (Enter to run, Ctrl+J for newline)",
                        id="gen-prompt-hint",
                    )
                    yield PromptTextArea("", id="gen-prompt")

            with TabPane("Video", id="tab-video"):
                with VerticalScroll(classes="section"):
                    yield Static(
                        (
                            "Alibaba video generation test page "
                            f"(default model: {ALIBABA_VIDEO_DEFAULT_MODEL})."
                        ),
                        id="video-hint",
                    )
                    with Horizontal(classes="form-row"):
                        yield Select(
                            options=[
                                ("text_to_video", VIDEO_TASK_TEXT2VIDEO),
                                ("image_to_video", VIDEO_TASK_IMAGE2VIDEO),
                            ],
                            value=VIDEO_TASK_TEXT2VIDEO,
                            id="video-task",
                        )
                        yield Select(
                            options=[
                                (ALIBABA_VIDEO_DEFAULT_MODEL, ALIBABA_VIDEO_DEFAULT_MODEL),
                            ],
                            value=ALIBABA_VIDEO_DEFAULT_MODEL,
                            id="video-model",
                        )
                        yield Select(
                            options=[
                                ("720P", "720P"),
                                ("1080P", "1080P"),
                            ],
                            value=ALIBABA_VIDEO_DEFAULT_RESOLUTION,
                            id="video-resolution",
                        )
                        yield Input(
                            placeholder="Duration (seconds)",
                            value=ALIBABA_VIDEO_DEFAULT_DURATION,
                            id="video-duration",
                        )
                    with Horizontal(classes="form-row"):
                        yield Input(
                            placeholder="Extra JSON path (optional)",
                            id="video-extra-json",
                            classes="full",
                        )
                    with Horizontal(classes="form-row", id="video-row-image"):
                        yield Input(
                            placeholder="Input image path / URL (required for image_to_video)",
                            id="video-input-image",
                            classes="full",
                        )
                    with Horizontal(classes="form-row"):
                        yield Select(
                            options=[
                                ("negative prompt: off", "off"),
                                ("negative prompt: on", "on"),
                            ],
                            value="off",
                            id="video-negative-enabled",
                        )
                        yield Input(
                            placeholder="Negative prompt",
                            id="video-negative-prompt",
                            classes="full",
                        )
                    yield Static("", id="video-guide")
                    yield Static("Ready.", id="video-status")
                    yield Static("", id="video-spacer")
                    yield Static(
                        "Prompt (Enter to run, Ctrl+J for newline)",
                        id="video-prompt-hint",
                    )
                    yield PromptTextArea("", id="video-prompt")

            with TabPane("Speech", id="tab-speech"):
                with VerticalScroll(classes="section"):
                    yield Static(
                        (
                            "Alibaba speech generation test page "
                            f"(default model: {ALIBABA_SPEECH_DEFAULT_MODEL})."
                        ),
                        id="speech-hint",
                    )
                    with Horizontal(classes="form-row"):
                        yield Select(
                            options=[(SPEECH_TASK_TEXT2SPEECH, SPEECH_TASK_TEXT2SPEECH)],
                            value=SPEECH_TASK_TEXT2SPEECH,
                            id="speech-task",
                        )
                        yield Select(
                            options=[
                                (ALIBABA_SPEECH_DEFAULT_MODEL, ALIBABA_SPEECH_DEFAULT_MODEL),
                            ],
                            value=ALIBABA_SPEECH_DEFAULT_MODEL,
                            id="speech-model",
                        )
                        yield Select(
                            options=[
                                (
                                    ALIBABA_SPEECH_MODE_SERVER_COMMIT,
                                    ALIBABA_SPEECH_MODE_SERVER_COMMIT,
                                ),
                                (ALIBABA_SPEECH_MODE_COMMIT, ALIBABA_SPEECH_MODE_COMMIT),
                            ],
                            value=ALIBABA_SPEECH_MODE_SERVER_COMMIT,
                            id="speech-mode",
                        )
                    with Horizontal(classes="form-row"):
                        yield Input(
                            placeholder="Voice name (required by realtime TTS)",
                            id="speech-voice",
                            classes="full",
                        )
                    with Horizontal(classes="form-row"):
                        yield Input(
                            placeholder="Extra JSON path (optional)",
                            id="speech-extra-json",
                            classes="full",
                        )
                    yield Static("", id="speech-guide")
                    yield Static("Ready.", id="speech-status")
                    yield Static("", id="speech-spacer")
                    yield Static(
                        "Prompt (Enter to run, Ctrl+J for newline)",
                        id="speech-prompt-hint",
                    )
                    yield PromptTextArea("", id="speech-prompt")

            with TabPane("Models", id="tab-models"):
                with VerticalScroll(classes="section"):
                    with Horizontal(classes="form-row"):
                        yield Select(
                            options=[
                                ("All providers", SELECT_ALL),
                                ("Alibaba", "alibaba"),
                                ("Google", "google"),
                                ("GLM", "glm"),
                            ],
                            value=SELECT_ALL,
                            id="models-provider",
                        )
                        yield Select(
                            options=[
                                ("All tasks", SELECT_ALL),
                                ("text_to_image", TASK_TEXT2IMAGE),
                                ("image_to_image", TASK_IMAGE2IMAGE),
                            ],
                            value=SELECT_ALL,
                            id="models-task",
                        )
                        yield Select(
                            options=[
                                ("All statuses", "all"),
                                ("Recommended only", "recommended"),
                            ],
                            value="all",
                            id="models-recommend",
                        )
                        yield Button("Refresh Models", id="refresh-models")
                        yield Button("Delete Selected", id="delete-model")
                    yield Static(
                        "Tip: choose provider/task/status filters, then press Refresh Models.",
                        id="models-hint",
                    )
                    yield Static(
                        f"Catalog snapshot: {CATALOG_SNAPSHOT_DATE}",
                        id="models-meta",
                    )
                    yield Static("Ready.", id="models-status")
                    yield DataTable(id="models-table")

            with TabPane("History", id="tab-history"):
                with VerticalScroll(classes="section"):
                    with Horizontal(classes="form-row"):
                        yield Select(
                            options=[
                                ("All providers", SELECT_ALL),
                                ("Alibaba", "alibaba"),
                                ("Google", "google"),
                                ("GLM", "glm"),
                            ],
                            value=SELECT_ALL,
                            id="history-provider",
                        )
                        yield Input(placeholder="Limit", value="20", id="history-limit")
                        yield Button("Refresh History", id="refresh-history")
                    yield Static(
                        "Tip: refresh list, select a row, then Show Details to inspect artifacts.",
                        id="history-hint",
                    )
                    yield DataTable(id="history-table")
                    with Horizontal(classes="form-row"):
                        yield Input(
                            placeholder="Run ID or full path",
                            id="history-run-id",
                            classes="full",
                        )
                        yield Button("Show Details", id="show-history-detail")
                    yield Pretty(
                        {"message": "Select a run and click Show Details."},
                        id="history-detail",
                    )

            with TabPane("Config", id="tab-config"):
                with VerticalScroll(classes="section"):
                    yield Static("Provider API Key Configuration", id="config-title")
                    yield Static(
                        "Tip: Load -> edit fields -> Apply Session (or Save .env + Apply).",
                        id="config-hint",
                    )
                    yield Static("", id="config-guide")
                    yield Static("", id="config-output-active")
                    with Horizontal(classes="form-row"):
                        yield Input(
                            placeholder="Output directory (used by generation + history)",
                            id="conf-output-dir",
                            classes="full",
                        )
                    with Horizontal(classes="form-row"):
                        yield Select(
                            options=[
                                ("png", "png"),
                                ("jpg", "jpg"),
                            ],
                            value="png",
                            id="conf-bin-format",
                        )
                        yield Select(
                            options=[
                                ("persist auto-crop input: off", "off"),
                                ("persist auto-crop input: on", "on"),
                            ],
                            value=PERSIST_PREPROCESSED_INPUT_DEFAULT,
                            id="conf-persist-preprocessed",
                        )
                        yield Select(
                            options=[
                                ("Alibaba auto-crop: off", "off"),
                                ("Alibaba auto-crop: on", "on"),
                            ],
                            value=AUTOCROP_DEFAULT,
                            id="conf-autocrop",
                        )
                    yield Static("Custom Model Registration", id="config-custom-model-title")
                    with Horizontal(classes="form-row"):
                        yield Select(
                            options=[
                                ("Alibaba", "alibaba"),
                                ("Google", "google"),
                                ("GLM", "glm"),
                            ],
                            value="alibaba",
                            id="conf-model-provider",
                        )
                        yield Input(
                            placeholder="Custom model ID",
                            id="conf-model-id",
                        )
                    with Horizontal(classes="form-row"):
                        yield Select(
                            options=[
                                ("text_to_image", TASK_TEXT2IMAGE),
                                ("image_to_image", TASK_IMAGE2IMAGE),
                            ],
                            value=TASK_TEXT2IMAGE,
                            id="conf-model-task",
                        )
                        yield Select(
                            options=[
                                ("recommend unset (optional)", SELECT_UNSET),
                                ("recommended", "yes"),
                                ("not recommended", "no"),
                            ],
                            value=SELECT_UNSET,
                            id="conf-model-recommend",
                        )
                        yield Button("Add Custom Model", id="conf-add-model")
                    with Horizontal(classes="form-row"):
                        yield Input(
                            placeholder="ALIBABA_API_KEY",
                            password=True,
                            id="conf-alibaba-key",
                        )
                    with Horizontal(classes="form-row"):
                        yield Input(
                            placeholder="GOOGLE_API_KEY",
                            password=True,
                            id="conf-google-key",
                        )
                    with Horizontal(classes="form-row"):
                        yield Input(
                            placeholder="GLM_API_KEY",
                            password=True,
                            id="conf-glm-key",
                        )
                    with Horizontal(classes="form-row"):
                        yield Button("Load Current Env", id="conf-load")
                        yield Button("Apply Session", id="conf-apply", variant="primary")
                        yield Button("Save .env + Apply", id="conf-save")
                    yield Static("Ready.", id="config-status")
        yield Footer()

    def on_mount(self) -> None:
        self._apply_mode_ui(self._select_value(self.query_one("#gen-mode", Select)))
        self._refresh_generate_model_selects()
        self._sync_negative_prompt_ui()
        self._sync_prompt_height()
        self._sync_video_prompt_height()
        self._sync_speech_prompt_height()
        self._sync_video_input_mode_ui()
        self._sync_video_negative_prompt_ui()
        self._refresh_video_guidance()
        self._refresh_speech_guidance()
        self._refresh_models_table()
        self._refresh_history_table()
        self._load_config_inputs_from_env()
        self._refresh_config_guidance()

    @on(Button.Pressed, "#refresh-models")
    def on_refresh_models(self) -> None:
        self._refresh_models_table()
        self._set_models_status("Models refreshed.")

    @on(Button.Pressed, "#delete-model")
    def on_delete_model(self) -> None:
        self._delete_selected_model()

    def on_key(self, event: Key) -> None:
        if event.key != "delete":
            return
        focused = self.focused
        if isinstance(focused, DataTable) and focused.id == "models-table":
            event.prevent_default()
            event.stop()
            self._delete_selected_model()

    def _delete_selected_model(self) -> None:
        entry = self._selected_models_entry()
        if entry is None:
            self._set_models_status("Select one model row to delete.")
            return
        if self._model_entry_source(entry) != "custom":
            self._set_models_status("Built-in models cannot be deleted. Only custom models can.")
            return

        provider = entry["provider"]
        model_id = entry["id"]
        tasks = [item.strip() for item in entry["tasks"].split(",") if item.strip()]
        deleted = 0
        for task_type in tasks:
            if delete_custom_model_entry(provider=provider, model_id=model_id, task_type=task_type):
                deleted += 1
        if deleted <= 0:
            self._set_models_status(
                f"Delete skipped: custom model not found ({provider}/{model_id})."
            )
            return

        self._refresh_models_table()
        self._refresh_generate_model_selects()
        self._set_models_status(f"Deleted custom model: {provider}/{model_id}.")

    @on(Button.Pressed, "#refresh-history")
    def on_refresh_history(self) -> None:
        self._refresh_history_table()

    @on(Button.Pressed, "#show-history-detail")
    def on_show_history_detail(self) -> None:
        run_id = self.query_one("#history-run-id", Input).value.strip()
        detail = self.query_one("#history-detail", Pretty)
        if not run_id:
            detail.update({"error": "run_id is required"})
            return
        try:
            run_dir = self._resolve_history_run(run_id)
            payload = load_history_run_details(run_dir)
            self._last_history_detail = payload
            detail.update(payload)
        except Exception as exc:  # noqa: BLE001
            detail.update({"error": str(exc)})

    @on(Button.Pressed, "#conf-load")
    def on_config_load(self) -> None:
        self._load_config_inputs_from_env()
        self._refresh_config_guidance()
        self._refresh_generate_guidance()
        self._set_config_status(
            "Loaded output dir, formats, auto-crop toggles, and API keys from environment."
        )

    @on(Button.Pressed, "#conf-apply")
    def on_config_apply(self) -> None:
        try:
            values, output_dir, bin_format, persist_preprocessed, auto_crop = (
                self._collect_config_values()
            )
        except Exception as exc:  # noqa: BLE001
            self._set_config_status(f"Invalid config: {exc}")
            self._refresh_config_guidance()
            return
        self._apply_api_key_values(values)
        self._apply_output_dir(output_dir)
        self._apply_bin_alias_format(bin_format)
        self._apply_persist_preprocessed_input(persist_preprocessed)
        self._apply_alibaba_autocrop(auto_crop)
        self._refresh_config_guidance()
        self._refresh_generate_guidance()
        self._set_config_status(
            "Applied output dir, formats, auto-crop toggles, and API keys to current session."
        )

    @on(Button.Pressed, "#conf-save")
    def on_config_save(self) -> None:
        try:
            values, output_dir, bin_format, persist_preprocessed, auto_crop = (
                self._collect_config_values()
            )
        except Exception as exc:  # noqa: BLE001
            self._set_config_status(f"Invalid config: {exc}")
            self._refresh_config_guidance()
            return
        resolved_output_dir = self._apply_output_dir(output_dir)
        self._apply_bin_alias_format(bin_format)
        self._apply_persist_preprocessed_input(persist_preprocessed)
        self._apply_alibaba_autocrop(auto_crop)
        self._save_config_to_env(
            values,
            resolved_output_dir,
            bin_format,
            persist_preprocessed,
            auto_crop,
        )
        self._apply_api_key_values(values)
        self._refresh_config_guidance()
        self._refresh_generate_guidance()
        self._set_config_status(f"Saved to {self._env_file_path()} and applied.")

    @on(Button.Pressed, "#conf-add-model")
    def on_config_add_custom_model(self) -> None:
        provider = self._select_value(self.query_one("#conf-model-provider", Select))
        model_id = self.query_one("#conf-model-id", Input).value.strip()
        task_type = self._select_value(self.query_one("#conf-model-task", Select))
        recommend_raw = self._select_value(self.query_one("#conf-model-recommend", Select))
        recommended: Optional[bool] = None
        if recommend_raw == "yes":
            recommended = True
        if recommend_raw == "no":
            recommended = False
        try:
            item = add_custom_model_entry(
                provider=provider,
                model_id=model_id,
                task_type=task_type,
                recommended=recommended,
            )
        except Exception as exc:  # noqa: BLE001
            self._set_config_status(f"Add custom model failed: {exc}")
            return

        self.query_one("#conf-model-id", Input).value = ""
        self._refresh_models_table()
        self._refresh_generate_model_selects()
        self._refresh_config_guidance()
        self._set_config_status(
            f"Added custom model: provider={item['provider']} id={item['id']} task={item['tasks']}"
        )

    @on(Input.Submitted, "#conf-model-id")
    def on_config_model_id_submitted(self) -> None:
        if self.query_one("#conf-model-id", Input).value.strip():
            self.on_config_add_custom_model()

    @on(Input.Changed, "#conf-output-dir")
    @on(Input.Changed, "#conf-alibaba-key")
    @on(Input.Changed, "#conf-google-key")
    @on(Input.Changed, "#conf-glm-key")
    @on(Input.Changed, "#conf-model-id")
    @on(Select.Changed, "#conf-bin-format")
    @on(Select.Changed, "#conf-persist-preprocessed")
    @on(Select.Changed, "#conf-autocrop")
    @on(Select.Changed, "#conf-model-provider")
    @on(Select.Changed, "#conf-model-task")
    @on(Select.Changed, "#conf-model-recommend")
    def on_config_field_changed(self) -> None:
        self._refresh_config_guidance()

    @on(PromptTextArea.Submit)
    async def on_prompt_submit(self, event: PromptTextArea.Submit) -> None:
        sender_id = (event.sender.id or "").strip()
        if sender_id == "gen-prompt":
            self._start_generate()
            return
        if sender_id == "video-prompt":
            self._start_video_generate()
            return
        if sender_id == "speech-prompt":
            self._start_speech_generate()

    async def on_resize(self, event: Resize) -> None:
        del event
        self._sync_prompt_height()
        self._sync_video_prompt_height()
        self._sync_speech_prompt_height()

    @on(TextArea.Changed, "#gen-prompt")
    def on_prompt_changed(self) -> None:
        self._sync_prompt_height()
        self._refresh_generate_guidance()

    @on(Input.Changed, "#gen-input-image")
    def on_generate_input_image_changed(self) -> None:
        self._refresh_generate_guidance()

    @on(Input.Changed, "#gen-prompts-file")
    def on_generate_prompts_file_changed(self) -> None:
        self._refresh_generate_guidance()

    @on(Input.Changed, "#gen-n")
    def on_generate_n_changed(self) -> None:
        self._refresh_generate_guidance()

    @on(Select.Changed, "#video-task")
    def on_video_task_changed(self) -> None:
        self._sync_video_input_mode_ui()
        self._refresh_video_guidance()

    @on(Select.Changed, "#video-negative-enabled")
    def on_video_negative_enabled_changed(self) -> None:
        self._sync_video_negative_prompt_ui()
        self._refresh_video_guidance()

    @on(TextArea.Changed, "#video-prompt")
    def on_video_prompt_changed(self) -> None:
        self._sync_video_prompt_height()
        self._refresh_video_guidance()

    @on(Input.Changed, "#video-input-image")
    @on(Input.Changed, "#video-duration")
    @on(Input.Changed, "#video-negative-prompt")
    @on(Input.Changed, "#video-extra-json")
    @on(Select.Changed, "#video-model")
    @on(Select.Changed, "#video-resolution")
    def on_video_field_changed(self) -> None:
        self._refresh_video_guidance()

    @on(TextArea.Changed, "#speech-prompt")
    def on_speech_prompt_changed(self) -> None:
        self._sync_speech_prompt_height()
        self._refresh_speech_guidance()

    @on(Input.Changed, "#speech-voice")
    @on(Input.Changed, "#speech-extra-json")
    @on(Select.Changed, "#speech-task")
    @on(Select.Changed, "#speech-model")
    @on(Select.Changed, "#speech-mode")
    def on_speech_field_changed(self) -> None:
        self._refresh_speech_guidance()

    @on(Select.Changed, "#gen-negative-enabled")
    def on_generate_negative_enabled_changed(self) -> None:
        self._sync_negative_prompt_ui()
        self._refresh_generate_guidance()

    @on(Input.Changed, "#gen-negative-prompt")
    def on_generate_negative_prompt_changed(self) -> None:
        self._refresh_generate_guidance()

    def _start_generate(self) -> None:
        if self._generate_task and not self._generate_task.done():
            self._set_generate_status("A generation task is already running.")
            return
        try:
            inputs = self._collect_generation_inputs()
        except Exception as exc:  # noqa: BLE001
            self._set_generate_status(f"Invalid input: {exc}")
            return
        mode = cast(str, inputs["mode"])
        self._set_generate_status(f"Running mode={mode} ...")
        self._set_generate_controls_disabled(True)
        self._generate_started_at = time.monotonic()
        self._generate_latest_log = self._build_pre_run_hint(inputs)
        self._attach_generate_log_handler()
        self._generate_task = asyncio.create_task(self._run_generate_worker(inputs))
        self._generate_progress_task = asyncio.create_task(self._run_generate_progress(mode))
        self._generate_watch_task = asyncio.create_task(self._wait_generate_done())

    def _build_pre_run_hint(self, inputs: Dict[str, Any]) -> str:
        task_type = cast(str, inputs["task_type"])
        if task_type != TASK_IMAGE2IMAGE:
            return ""
        mode = cast(str, inputs["mode"])
        providers = [cast(str, inputs["provider"])]
        if mode == RUN_MODE_COMPARE:
            providers.append(cast(str, inputs["provider_b"]))
        if "alibaba" in providers:
            state = "enabled" if is_alibaba_autocrop_enabled() else "disabled"
            return f"INFO Alibaba image_to_image: MVP auto-crop is {state}."
        return ""

    async def _run_generate_worker(self, inputs: Dict[str, Any]) -> str:
        mode = cast(str, inputs["mode"])
        result = await asyncio.to_thread(self._run_generate_mode, inputs)
        return self._format_generate_result(mode, result)

    async def _wait_generate_done(self) -> None:
        if not self._generate_task:
            return
        try:
            message = await self._generate_task
            self._set_generate_status(message)
            self._refresh_history_table()
        except Exception as exc:  # noqa: BLE001
            self._set_generate_status(f"Failed: {exc}")
        finally:
            if self._generate_progress_task and not self._generate_progress_task.done():
                self._generate_progress_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._generate_progress_task
            self._detach_generate_log_handler()
            self._set_generate_controls_disabled(False)
            self._generate_task = None
            self._generate_watch_task = None
            self._generate_progress_task = None

    async def _run_generate_progress(self, mode: str) -> None:
        spinner = "|/-\\"
        index = 0
        while self._generate_task and not self._generate_task.done():
            elapsed = int(time.monotonic() - self._generate_started_at)
            line = f"{spinner[index % len(spinner)]} Running mode={mode} ... {elapsed}s"
            if self._generate_latest_log:
                line += f"\nlog: {self._generate_latest_log}"
            self._set_generate_status(line)
            index += 1
            await asyncio.sleep(0.2)

    def _start_video_generate(self) -> None:
        if self._video_task and not self._video_task.done():
            self._set_video_status("A video task is already running.")
            return
        try:
            inputs = self._collect_video_inputs()
        except Exception as exc:  # noqa: BLE001
            self._set_video_status(f"Invalid input: {exc}")
            return
        self._set_video_status("Running video generation ...")
        self._set_video_controls_disabled(True)
        self._video_started_at = time.monotonic()
        self._video_task = asyncio.create_task(self._run_video_worker(inputs))
        self._video_progress_task = asyncio.create_task(self._run_video_progress())
        self._video_watch_task = asyncio.create_task(self._wait_video_done())

    async def _run_video_worker(self, inputs: Dict[str, Any]) -> str:
        return await asyncio.to_thread(self._run_video_mode, inputs)

    async def _wait_video_done(self) -> None:
        if not self._video_task:
            return
        try:
            message = await self._video_task
            self._set_video_status(message)
            self._refresh_history_table()
        except Exception as exc:  # noqa: BLE001
            self._set_video_status(f"Failed: {exc}")
        finally:
            if self._video_progress_task and not self._video_progress_task.done():
                self._video_progress_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._video_progress_task
            self._set_video_controls_disabled(False)
            self._sync_video_input_mode_ui()
            self._sync_video_negative_prompt_ui()
            self._refresh_video_guidance()
            self._video_task = None
            self._video_watch_task = None
            self._video_progress_task = None

    async def _run_video_progress(self) -> None:
        spinner = "|/-\\"
        index = 0
        while self._video_task and not self._video_task.done():
            elapsed = int(time.monotonic() - self._video_started_at)
            line = f"{spinner[index % len(spinner)]} Running video generation ... {elapsed}s"
            self._set_video_status(line)
            index += 1
            await asyncio.sleep(0.2)

    def _start_speech_generate(self) -> None:
        if self._speech_task and not self._speech_task.done():
            self._set_speech_status("A speech task is already running.")
            return
        try:
            inputs = self._collect_speech_inputs()
        except Exception as exc:  # noqa: BLE001
            self._set_speech_status(f"Invalid input: {exc}")
            return
        self._set_speech_status("Running speech generation ...")
        self._set_speech_controls_disabled(True)
        self._speech_started_at = time.monotonic()
        self._speech_task = asyncio.create_task(self._run_speech_worker(inputs))
        self._speech_progress_task = asyncio.create_task(self._run_speech_progress())
        self._speech_watch_task = asyncio.create_task(self._wait_speech_done())

    async def _run_speech_worker(self, inputs: Dict[str, Any]) -> str:
        return await asyncio.to_thread(self._run_speech_mode, inputs)

    async def _wait_speech_done(self) -> None:
        if not self._speech_task:
            return
        try:
            message = await self._speech_task
            self._set_speech_status(message)
            self._refresh_history_table()
        except Exception as exc:  # noqa: BLE001
            self._set_speech_status(f"Failed: {exc}")
        finally:
            if self._speech_progress_task and not self._speech_progress_task.done():
                self._speech_progress_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._speech_progress_task
            self._set_speech_controls_disabled(False)
            self._refresh_speech_guidance()
            self._speech_task = None
            self._speech_watch_task = None
            self._speech_progress_task = None

    async def _run_speech_progress(self) -> None:
        spinner = "|/-\\"
        index = 0
        while self._speech_task and not self._speech_task.done():
            elapsed = int(time.monotonic() - self._speech_started_at)
            line = f"{spinner[index % len(spinner)]} Running speech generation ... {elapsed}s"
            self._set_speech_status(line)
            index += 1
            await asyncio.sleep(0.2)

    def _collect_speech_inputs(self) -> Dict[str, Any]:
        task_type = self._select_value(self.query_one("#speech-task", Select))
        model = self._select_value(self.query_one("#speech-model", Select))
        mode = self._select_value(self.query_one("#speech-mode", Select))
        voice = self.query_one("#speech-voice", Input).value.strip()
        prompt = self.query_one("#speech-prompt", TextArea).text.strip()
        extra_json_path = self.query_one("#speech-extra-json", Input).value.strip() or None

        if not os.getenv("ALIBABA_API_KEY", "").strip():
            raise ValueError("Missing API key env var(s): ALIBABA_API_KEY")
        if task_type != SPEECH_TASK_TEXT2SPEECH:
            raise ValueError("Unsupported speech task type")
        if not model:
            raise ValueError("Model is required")
        if mode not in {ALIBABA_SPEECH_MODE_SERVER_COMMIT, ALIBABA_SPEECH_MODE_COMMIT}:
            raise ValueError("Unsupported speech mode")
        if not voice:
            raise ValueError("Voice is required")
        if not prompt:
            raise ValueError("Prompt is required")

        return {
            "provider": "alibaba",
            "task_type": task_type,
            "model": model,
            "mode": mode,
            "voice": voice,
            "prompt": prompt,
            "extra": read_json_file(extra_json_path),
        }

    def _run_speech_mode(self, inputs: Dict[str, Any]) -> str:
        result = self._run_alibaba_speech_realtime(inputs)
        run_dir = self._persist_speech_run(inputs, result)
        preview_url = self._first_speech_preview_url(run_dir)
        message = f"Success. Saved to: {run_dir}"
        if preview_url:
            message += f"\nPreview URL (Ctrl+Left Click): {preview_url}"
        return message

    def _run_alibaba_speech_realtime(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        try:
            import dashscope
            from dashscope.audio.qwen_tts_realtime import (
                AudioFormat,
                QwenTtsRealtime,
                QwenTtsRealtimeCallback,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Speech page requires dashscope SDK. Install with: pip install dashscope"
            ) from exc

        api_key = os.getenv("ALIBABA_API_KEY", "").strip()
        dashscope.api_key = api_key

        class _SpeechCallback(QwenTtsRealtimeCallback):
            def __init__(self) -> None:
                super().__init__()
                self.done_event = threading.Event()
                self.response_done_event = threading.Event()
                self.errors: List[str] = []
                self.audio_bytes = bytearray()

            def on_event(self, response) -> None:  # type: ignore[no-untyped-def]
                try:
                    if not isinstance(response, dict):
                        return
                    event_type = str(response.get("type", "")).strip()
                    if event_type == "response.audio.delta":
                        delta = response.get("delta")
                        if isinstance(delta, str) and delta:
                            self.audio_bytes.extend(base64.b64decode(delta))
                        return
                    if event_type == "response.done":
                        self.response_done_event.set()
                        return
                    if event_type == "session.finished":
                        self.done_event.set()
                        return
                    if event_type == "error":
                        self.errors.append(json.dumps(response, ensure_ascii=False))
                        self.done_event.set()
                        self.response_done_event.set()
                except Exception as exc:  # noqa: BLE001
                    self.errors.append(str(exc))
                    self.done_event.set()
                    self.response_done_event.set()

            def wait_response_done(self, timeout_seconds: int) -> bool:
                ok = self.response_done_event.wait(timeout_seconds)
                self.response_done_event.clear()
                return ok

            def wait_done(self, timeout_seconds: int) -> bool:
                return self.done_event.wait(timeout_seconds)

        callback = _SpeechCallback()
        url = self._resolve_alibaba_speech_ws_url()
        qwen = QwenTtsRealtime(
            model=cast(str, inputs["model"]),
            callback=callback,
            url=url,
        )
        started = time.perf_counter()
        try:
            qwen.connect()
            qwen.update_session(
                voice=cast(str, inputs["voice"]),
                mode=cast(str, inputs["mode"]),
                response_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
            )
            extra = cast(Dict[str, Any], inputs.get("extra", {}))
            if extra:
                qwen.update_session(**extra)

            chunks = self._speech_text_chunks(cast(str, inputs["prompt"]))
            mode = cast(str, inputs["mode"])
            if mode == ALIBABA_SPEECH_MODE_COMMIT:
                for chunk in chunks:
                    qwen.append_text(chunk)
                    qwen.commit()
                    if not callback.wait_response_done(60):
                        raise TimeoutError("Speech commit mode timed out waiting response.done")
            else:
                for chunk in chunks:
                    qwen.append_text(chunk)
                qwen.finish()

            if not callback.wait_done(180):
                raise TimeoutError("Speech session timeout waiting session.finished")
        finally:
            with contextlib.suppress(Exception):
                qwen.close()

        if callback.errors:
            raise RuntimeError(f"Speech generation failed: {callback.errors[0]}")
        audio_payload = bytes(callback.audio_bytes)
        if not audio_payload:
            raise RuntimeError("Speech generation returned empty audio payload")

        request_id = ""
        with contextlib.suppress(Exception):
            request_id = str(qwen.get_session_id() or "").strip()
        if not request_id:
            request_id = f"speech_{int(time.time())}"
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "request_id": request_id,
            "audio_bytes": audio_payload,
            "latency_ms": latency_ms,
            "events": {"errors": callback.errors},
        }

    @staticmethod
    def _speech_text_chunks(text: str) -> List[str]:
        chunks = [line.strip() for line in text.splitlines() if line.strip()]
        if chunks:
            return chunks
        stripped = text.strip()
        return [stripped] if stripped else []

    def _persist_speech_run(self, inputs: Dict[str, Any], result: Dict[str, Any]) -> Path:
        output_root = ensure_dir(self.output_root)
        request_id = cast(str, result.get("request_id") or f"speech_{int(time.time())}")
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        task_type = cast(str, inputs["task_type"])
        run_dir = ensure_dir(output_root / f"{timestamp}_alibaba_{task_type}_{request_id}")

        request_payload = {
            "provider": "alibaba",
            "model": inputs["model"],
            "task_type": task_type,
            "mode": inputs["mode"],
            "voice": inputs["voice"],
            "prompt": inputs["prompt"],
            "extra": inputs.get("extra", {}),
        }

        audio_dir = ensure_dir(run_dir / "audios")
        audio_path = audio_dir / "audio_01.pcm"
        audio_bytes = cast(bytes, result["audio_bytes"])
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)
        saved_files = [str(audio_path)]

        response_record = {
            "request_id": request_id,
            "provider": "alibaba",
            "model": inputs["model"],
            "task_type": task_type,
            "audios": saved_files,
            "images": saved_files,  # Keep history list compatibility.
            "latency_ms": result.get("latency_ms", 0),
            "raw_response": result.get("events", {}),
        }

        (run_dir / "request.json").write_text(
            json.dumps(request_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "response.json").write_text(
            json.dumps(response_record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "saved_audios.json").write_text(
            json.dumps({"saved_files": saved_files}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "saved_images.json").write_text(
            json.dumps({"saved_files": saved_files}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return run_dir

    def _first_speech_preview_url(self, run_dir: Path) -> str:
        audio_dir = run_dir / "audios"
        if not audio_dir.exists():
            return ""
        for ext in ("*.wav", "*.mp3", "*.pcm", "*.flac"):
            matches = sorted(audio_dir.glob(ext))
            if matches:
                return matches[0].resolve().as_uri()
        return ""

    def _resolve_alibaba_speech_ws_url(self) -> str:
        explicit = os.getenv("ALIBABA_SPEECH_WS_URL", "").strip()
        if explicit:
            return explicit
        region = os.getenv("ALIBABA_REGION", "intl").strip().lower()
        return ALIBABA_SPEECH_WS_HOSTS.get(region, ALIBABA_SPEECH_WS_HOSTS["intl"])

    def _run_video_mode(self, inputs: Dict[str, Any]) -> str:
        payload = self._build_alibaba_video_payload(inputs)
        response_payload = self._run_alibaba_video_task(payload)
        run_dir = self._persist_video_run(inputs, response_payload)
        preview_url = self._first_video_preview_url(run_dir)
        message = f"Success. Saved to: {run_dir}"
        if preview_url:
            message += f"\nPreview URL (Ctrl+Left Click): {preview_url}"
        return message

    def _collect_video_inputs(self) -> Dict[str, Any]:
        task_type = self._select_value(self.query_one("#video-task", Select))
        model = self._select_value(self.query_one("#video-model", Select))
        prompt = self.query_one("#video-prompt", TextArea).text.strip()
        input_image = self.query_one("#video-input-image", Input).value.strip() or None
        resolution = self._select_value(self.query_one("#video-resolution", Select))
        duration_raw = self.query_one("#video-duration", Input).value.strip()
        negative_enabled = (
            self._select_value(self.query_one("#video-negative-enabled", Select)) == "on"
        )
        negative_prompt_raw = self.query_one("#video-negative-prompt", Input).value.strip()
        extra_json_path = self.query_one("#video-extra-json", Input).value.strip() or None

        if not os.getenv("ALIBABA_API_KEY", "").strip():
            raise ValueError("Missing API key env var(s): ALIBABA_API_KEY")
        if task_type not in {VIDEO_TASK_TEXT2VIDEO, VIDEO_TASK_IMAGE2VIDEO}:
            raise ValueError("Unsupported video task type")
        if not model:
            raise ValueError("Model is required")
        if not prompt:
            raise ValueError("Prompt is required")
        if task_type == VIDEO_TASK_IMAGE2VIDEO and not input_image:
            raise ValueError("Input image is required for image_to_video")
        if not duration_raw.isdigit():
            raise ValueError("Duration must be an integer")
        duration = int(duration_raw)
        if duration <= 0:
            raise ValueError("Duration must be > 0")
        negative_prompt: Optional[str] = None
        if negative_enabled:
            if not negative_prompt_raw:
                raise ValueError("Negative prompt is required when switch is on")
            negative_prompt = negative_prompt_raw

        return {
            "provider": "alibaba",
            "task_type": task_type,
            "model": model,
            "prompt": prompt,
            "input_image": input_image,
            "resolution": resolution,
            "duration": duration,
            "negative_prompt": negative_prompt,
            "extra": read_json_file(extra_json_path),
        }

    def _build_alibaba_video_payload(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        input_payload: Dict[str, Any] = {"prompt": cast(str, inputs["prompt"])}
        input_image = cast(Optional[str], inputs["input_image"])
        if input_image:
            image_info = parse_input_image(input_image)
            if not image_info:
                raise ValueError("Invalid input image format")
            input_payload["img_url"] = image_info["value"]

        parameters: Dict[str, Any] = {
            "resolution": cast(str, inputs["resolution"]),
            "duration": cast(int, inputs["duration"]),
        }
        negative_prompt = cast(Optional[str], inputs.get("negative_prompt"))
        if negative_prompt:
            parameters["negative_prompt"] = negative_prompt

        payload: Dict[str, Any] = {
            "model": cast(str, inputs["model"]),
            "input": input_payload,
            "parameters": parameters,
        }
        extra = cast(Dict[str, Any], inputs.get("extra", {}))
        if extra:
            payload.update(extra)
        return payload

    def _run_alibaba_video_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        api_key = os.getenv("ALIBABA_API_KEY", "").strip()
        if not api_key:
            raise ValueError("ALIBABA_API_KEY is missing")
        url = self._resolve_alibaba_video_url()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }

        started = time.perf_counter()
        create_resp = requests.post(url, headers=headers, json=payload, timeout=120)
        create_raw = self._json_or_text(create_resp)
        if not create_resp.ok:
            raise RuntimeError(
                "alibaba video create error "
                f"status={create_resp.status_code} body={str(create_raw)[:500]}"
            )

        task_id = self._extract_task_id(create_raw)
        if not task_id:
            videos = self._extract_video_urls(create_raw)
            if videos:
                latency_ms = int((time.perf_counter() - started) * 1000)
                return {
                    "request_id": f"video_{int(time.time())}",
                    "create_task": create_raw,
                    "task_result": create_raw,
                    "videos": videos,
                    "latency_ms": latency_ms,
                }
            raise RuntimeError(f"alibaba video create missing task_id: {create_raw}")

        poll_url = self._build_video_task_url(url, task_id)
        poll_headers = {
            "Authorization": f"Bearer {api_key}",
        }
        poll_interval = int(os.getenv("ALIBABA_POLL_INTERVAL_SECONDS", "5"))
        poll_timeout = int(os.getenv("ALIBABA_POLL_TIMEOUT_SECONDS", "300"))
        deadline = time.monotonic() + poll_timeout
        while time.monotonic() < deadline:
            poll_resp = requests.get(poll_url, headers=poll_headers, timeout=120)
            poll_raw = self._json_or_text(poll_resp)
            if not poll_resp.ok:
                raise RuntimeError(
                    "alibaba video poll error "
                    f"status={poll_resp.status_code} body={str(poll_raw)[:500]}"
                )
            status = self._extract_task_status(poll_raw)
            if status in {"SUCCEEDED", "SUCCESS"}:
                latency_ms = int((time.perf_counter() - started) * 1000)
                videos = self._extract_video_urls(poll_raw)
                return {
                    "request_id": task_id,
                    "create_task": create_raw,
                    "task_result": poll_raw,
                    "videos": videos,
                    "latency_ms": latency_ms,
                }
            if status in {"FAILED", "CANCELED", "CANCELLED"}:
                raise RuntimeError(f"alibaba video task failed: {poll_raw}")
            time.sleep(max(1, poll_interval))

        raise TimeoutError(f"alibaba video task poll timeout after {poll_timeout}s")

    def _persist_video_run(self, inputs: Dict[str, Any], response_payload: Dict[str, Any]) -> Path:
        output_root = ensure_dir(self.output_root)
        request_id = cast(str, response_payload.get("request_id") or f"video_{int(time.time())}")
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        task_type = cast(str, inputs["task_type"])
        run_dir = ensure_dir(output_root / f"{timestamp}_alibaba_{task_type}_{request_id}")

        request_payload = {
            "provider": "alibaba",
            "model": inputs["model"],
            "task_type": task_type,
            "prompt": inputs["prompt"],
            "negative_prompt": inputs.get("negative_prompt"),
            "input_image": inputs.get("input_image"),
            "resolution": inputs.get("resolution"),
            "duration": inputs.get("duration"),
            "extra": inputs.get("extra", {}),
        }
        videos = cast(List[str], response_payload.get("videos", []))
        response_record = {
            "request_id": request_id,
            "provider": "alibaba",
            "model": inputs["model"],
            "task_type": task_type,
            "videos": videos,
            "images": videos,  # Keep history compatibility (images count column).
            "latency_ms": response_payload.get("latency_ms", 0),
            "raw_response": {
                "create_task": response_payload.get("create_task", {}),
                "task_result": response_payload.get("task_result", {}),
            },
        }

        (run_dir / "request.json").write_text(
            json.dumps(request_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "response.json").write_text(
            json.dumps(response_record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        saved_files = self._save_videos(run_dir, videos)
        (run_dir / "saved_videos.json").write_text(
            json.dumps({"saved_files": saved_files}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "saved_images.json").write_text(
            json.dumps({"saved_files": saved_files}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return run_dir

    def _save_videos(self, run_dir: Path, videos: List[str]) -> List[str]:
        saved_files: List[str] = []
        videos_dir = ensure_dir(run_dir / "videos")
        for index, item in enumerate(videos, start=1):
            filename = f"video_{index:02d}"
            if item.startswith("http://") or item.startswith("https://"):
                target = videos_dir / f"{filename}.mp4"
                try:
                    resp = requests.get(item, timeout=120)
                    resp.raise_for_status()
                    with open(target, "wb") as f:
                        f.write(resp.content)
                    saved_files.append(str(target))
                except Exception:  # noqa: BLE001
                    txt_target = videos_dir / f"{filename}.url.txt"
                    txt_target.write_text(item, encoding="utf-8")
                    saved_files.append(str(txt_target))
                continue

            if item.startswith("data:video/") and "," in item:
                _, b64 = item.split(",", 1)
                target = videos_dir / f"{filename}.mp4"
                try:
                    with open(target, "wb") as f:
                        f.write(base64.b64decode(b64))
                    saved_files.append(str(target))
                except Exception:  # noqa: BLE001
                    txt_target = videos_dir / f"{filename}.txt"
                    txt_target.write_text(item, encoding="utf-8")
                    saved_files.append(str(txt_target))
                continue

            txt_target = videos_dir / f"{filename}.txt"
            txt_target.write_text(item, encoding="utf-8")
            saved_files.append(str(txt_target))
        return saved_files

    def _first_video_preview_url(self, run_dir: Path) -> str:
        videos_dir = run_dir / "videos"
        if videos_dir.exists():
            for ext in ("*.mp4", "*.mov", "*.webm"):
                matches = sorted(videos_dir.glob(ext))
                if matches:
                    return matches[0].resolve().as_uri()
            for txt in sorted(videos_dir.glob("*.url.txt")):
                remote = txt.read_text(encoding="utf-8").strip()
                if remote.startswith("http://") or remote.startswith("https://"):
                    return remote
        response_path = run_dir / "response.json"
        if response_path.exists():
            try:
                payload = json.loads(response_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return ""
            videos = payload.get("videos", [])
            if isinstance(videos, list):
                for item in videos:
                    if isinstance(item, str) and (
                        item.startswith("http://") or item.startswith("https://")
                    ):
                        return item
        return ""

    def _resolve_alibaba_video_url(self) -> str:
        explicit = os.getenv("ALIBABA_VIDEO_URL", "").strip()
        if explicit:
            return explicit
        region = os.getenv("ALIBABA_REGION", "intl").strip().lower()
        host = ALIBABA_VIDEO_HOSTS.get(region, ALIBABA_VIDEO_HOSTS["intl"])
        return f"{host}{ALIBABA_VIDEO_PATH}"

    def _build_video_task_url(self, create_url: str, task_id: str) -> str:
        parts = urlsplit(create_url)
        return f"{parts.scheme}://{parts.netloc}{ALIBABA_VIDEO_TASKS_PATH}/{task_id}"

    @staticmethod
    def _extract_task_id(raw: Any) -> str:
        if isinstance(raw, dict):
            output = raw.get("output")
            if isinstance(output, dict):
                value = output.get("task_id")
                if isinstance(value, str) and value.strip():
                    return value.strip()
            value = raw.get("task_id")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _extract_task_status(raw: Any) -> str:
        if isinstance(raw, dict):
            output = raw.get("output")
            if isinstance(output, dict):
                value = output.get("task_status")
                if isinstance(value, str):
                    return value.upper()
            value = raw.get("task_status")
            if isinstance(value, str):
                return value.upper()
        return "UNKNOWN"

    def _extract_video_urls(self, raw: Any) -> List[str]:
        results: List[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    if isinstance(value, str) and self._looks_like_video_url(key, value):
                        results.append(value)
                    else:
                        walk(value)
                return
            if isinstance(node, list):
                for item in node:
                    walk(item)

        walk(raw)
        deduped: List[str] = []
        seen = set()
        for item in results:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped

    @staticmethod
    def _looks_like_video_url(key: str, value: str) -> bool:
        low_key = key.lower()
        low_val = value.lower()
        if low_val.startswith("http://") or low_val.startswith("https://"):
            return any(
                mark in low_key
                for mark in ("video", "url", "file", "output", "result", "generated")
            )
        if low_val.startswith("data:video/"):
            return True
        return False

    @staticmethod
    def _json_or_text(response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {"raw_text": response.text}

    @on(Select.Changed, "#gen-mode")
    def on_generate_mode_changed(self) -> None:
        mode = self._select_value(self.query_one("#gen-mode", Select))
        self._apply_mode_ui(mode)

    @on(Select.Changed, "#gen-provider")
    def on_generate_provider_changed(self) -> None:
        self._refresh_generate_model_selects()

    @on(Select.Changed, "#gen-model")
    def on_generate_model_changed(self) -> None:
        self._refresh_generate_size_selects()

    @on(Select.Changed, "#gen-provider-b")
    def on_generate_provider_b_changed(self) -> None:
        self._refresh_generate_model_selects()

    @on(Select.Changed, "#gen-model-b")
    def on_generate_model_b_changed(self) -> None:
        self._refresh_generate_size_selects()

    @on(Select.Changed, "#gen-task")
    def on_generate_task_changed(self) -> None:
        self._refresh_generate_model_selects()

    @on(Select.Changed, "#gen-size-group")
    def on_generate_size_group_changed(self) -> None:
        self._refresh_generate_size_selects()

    @on(Select.Changed, "#gen-width")
    def on_generate_width_changed(self) -> None:
        self._refresh_generate_height_select()

    @on(Select.Changed, "#gen-height")
    def on_generate_height_changed(self) -> None:
        self._update_generate_size_hint()

    def _apply_mode_ui(self, mode: str) -> None:
        self.query_one("#gen-row-compare", Horizontal).display = mode == RUN_MODE_COMPARE
        self.query_one("#gen-row-batch", Horizontal).display = mode == RUN_MODE_BATCH
        self._update_prompt_hint(mode)
        self._refresh_generate_guidance()

    def action_copy_focus(self) -> None:
        text = self._extract_copy_text()
        if not text:
            self._set_generate_status("Nothing copyable in current focus.")
            return
        try:
            self._copy_to_clipboard(text)
        except Exception as exc:  # noqa: BLE001
            self._set_generate_status(f"Copy failed: {exc}")
            return
        self._set_generate_status("Copied current content to clipboard.")

    def _update_prompt_hint(self, mode: str) -> None:
        hint = "Prompt (Enter to run, Ctrl+J for newline)"
        if mode == RUN_MODE_BATCH:
            hint = "Prompt (optional in batch; Enter to run, Ctrl+J for newline)"
        self.query_one("#gen-prompt-hint", Static).update(hint)

    def _negative_prompt_enabled(self) -> bool:
        return self._select_value(self.query_one("#gen-negative-enabled", Select)) == "on"

    def _sync_negative_prompt_ui(self) -> None:
        enabled = self._negative_prompt_enabled()
        self.query_one("#gen-negative-prompt", Input).disabled = not enabled

    def _refresh_generate_guidance(self) -> None:
        mode = self._select_value(self.query_one("#gen-mode", Select))
        task_type = self._select_value(self.query_one("#gen-task", Select))
        provider = self._select_value(self.query_one("#gen-provider", Select))
        model = self._select_value(self.query_one("#gen-model", Select))
        provider_b = self._select_value(self.query_one("#gen-provider-b", Select))
        model_b = self._select_value(self.query_one("#gen-model-b", Select))
        prompt = self.query_one("#gen-prompt", TextArea).text.strip()
        prompts_file = self.query_one("#gen-prompts-file", Input).value.strip()
        input_image = self.query_one("#gen-input-image", Input).value.strip()
        n_raw = self.query_one("#gen-n", Input).value.strip() or "1"
        negative_enabled = self._negative_prompt_enabled()
        negative_prompt = self.query_one("#gen-negative-prompt", Input).value.strip()
        size = self._selected_generate_size() or "unknown"
        group = self._select_value(self.query_one("#gen-size-group", Select)) or SIZE_GROUP_ALL

        missing_required: List[str] = []
        warnings: List[str] = []
        if not model or model == SELECT_NONE_MODEL:
            missing_required.append("model id")
        if task_type == TASK_IMAGE2IMAGE and not input_image:
            missing_required.append("input image path/url")
        if mode in {RUN_MODE_SINGLE, RUN_MODE_COMPARE} and not prompt:
            missing_required.append("prompt")
        if mode == RUN_MODE_COMPARE and (
            not provider_b or not model_b or model_b == SELECT_NONE_MODEL
        ):
            missing_required.append("provider/model B")
        if mode == RUN_MODE_BATCH and not prompts_file:
            missing_required.append("prompts file")
        if negative_enabled and not negative_prompt:
            missing_required.append("negative prompt")
        try:
            if int(n_raw) <= 0:
                missing_required.append("n > 0")
        except ValueError:
            missing_required.append("valid n")

        missing_keys = self._missing_api_key_env_vars(mode, provider, provider_b)
        if missing_keys:
            missing_required.append(f"api key ({', '.join(missing_keys)})")

        if mode == RUN_MODE_BATCH and prompt:
            warnings.append("prompt box is ignored in batch mode (uses prompts file only)")
        if mode == RUN_MODE_COMPARE and provider == provider_b and model == model_b:
            warnings.append("A/B targets are identical; comparison result may be redundant")
        if negative_enabled:
            providers = [provider]
            if mode == RUN_MODE_COMPARE:
                providers.append(provider_b)
            if "google" in providers:
                warnings.append("negative prompt is not mapped for Google in current adapter")

        lines = [
            f"Flow: mode={mode} | task={task_type} | provider={provider}",
            f"Size: {size} | group={group} | n={n_raw}",
        ]
        lines.append(f"Negative prompt: {'on' if negative_enabled else 'off'}")
        if mode == RUN_MODE_SINGLE:
            lines.append("Steps: choose provider/model/task -> fill prompt -> Enter to run.")
        elif mode == RUN_MODE_COMPARE:
            lines.append("Steps: set A/B provider+model -> fill prompt -> Enter to run.")
        else:
            lines.append("Steps: choose provider/model -> set prompts file -> Enter to run.")

        if missing_required:
            self._set_generate_guide_state("error")
            lines.append(f"ERROR Missing required: {'; '.join(missing_required)}")
        elif warnings:
            self._set_generate_guide_state("warn")
            lines.append(f"WARN {'; '.join(warnings)}")
        else:
            self._set_generate_guide_state("ready")
            lines.append("READY Press Enter in prompt box to start generation.")

        if missing_required and warnings:
            lines.append(f"WARN {'; '.join(warnings)}")
        if mode == RUN_MODE_BATCH:
            lines.append("Batch: prompt box is optional; prompts file is line-based input.")
        lines.append("Shortcuts: Enter=Run, Ctrl+J=Newline, Ctrl+C=Copy focused.")
        self.query_one("#gen-guide", Static).update("\n".join(lines))

    def _set_generate_guide_state(self, state: str) -> None:
        guide = self.query_one("#gen-guide", Static)
        guide.remove_class("guide-error")
        guide.remove_class("guide-warn")
        guide.remove_class("guide-ready")
        if state == "error":
            guide.add_class("guide-error")
            return
        if state == "warn":
            guide.add_class("guide-warn")
            return
        guide.add_class("guide-ready")

    def _set_video_guide_state(self, state: str) -> None:
        guide = self.query_one("#video-guide", Static)
        guide.remove_class("guide-error")
        guide.remove_class("guide-warn")
        guide.remove_class("guide-ready")
        if state == "error":
            guide.add_class("guide-error")
            return
        if state == "warn":
            guide.add_class("guide-warn")
            return
        guide.add_class("guide-ready")

    def _set_speech_guide_state(self, state: str) -> None:
        guide = self.query_one("#speech-guide", Static)
        guide.remove_class("guide-error")
        guide.remove_class("guide-warn")
        guide.remove_class("guide-ready")
        if state == "error":
            guide.add_class("guide-error")
            return
        if state == "warn":
            guide.add_class("guide-warn")
            return
        guide.add_class("guide-ready")

    def _sync_video_input_mode_ui(self) -> None:
        task_type = self._select_value(self.query_one("#video-task", Select))
        self.query_one("#video-row-image", Horizontal).display = task_type == VIDEO_TASK_IMAGE2VIDEO

    def _sync_video_negative_prompt_ui(self) -> None:
        enabled = self._select_value(self.query_one("#video-negative-enabled", Select)) == "on"
        self.query_one("#video-negative-prompt", Input).disabled = not enabled

    def _refresh_video_guidance(self) -> None:
        task_type = self._select_value(self.query_one("#video-task", Select))
        model = self._select_value(self.query_one("#video-model", Select))
        prompt = self.query_one("#video-prompt", TextArea).text.strip()
        input_image = self.query_one("#video-input-image", Input).value.strip()
        duration_raw = self.query_one("#video-duration", Input).value.strip()
        resolution = self._select_value(self.query_one("#video-resolution", Select))
        negative_enabled = (
            self._select_value(self.query_one("#video-negative-enabled", Select)) == "on"
        )
        negative_prompt = self.query_one("#video-negative-prompt", Input).value.strip()

        errors: List[str] = []
        warnings: List[str] = []
        if not os.getenv("ALIBABA_API_KEY", "").strip():
            errors.append("ALIBABA_API_KEY is missing")
        if not prompt:
            errors.append("prompt is required")
        if task_type == VIDEO_TASK_IMAGE2VIDEO and not input_image:
            errors.append("input image is required for image_to_video")
        if not duration_raw.isdigit():
            errors.append("duration must be integer")
        elif int(duration_raw) <= 0:
            errors.append("duration must be > 0")
        if negative_enabled and not negative_prompt:
            errors.append("negative prompt is required when switch is on")
        if model != ALIBABA_VIDEO_DEFAULT_MODEL:
            warnings.append("non-default model selected")

        lines = [
            f"Flow: provider=alibaba | task={task_type} | model={model}",
            f"Params: resolution={resolution} | duration={duration_raw or '?'}s",
            f"Negative prompt: {'on' if negative_enabled else 'off'}",
        ]
        if errors:
            self._set_video_guide_state("error")
            lines.append(f"ERROR {'; '.join(errors)}")
        elif warnings:
            self._set_video_guide_state("warn")
            lines.append(f"WARN {'; '.join(warnings)}")
        else:
            self._set_video_guide_state("ready")
            lines.append("READY Press Enter in prompt box to start video generation.")
        lines.append("Supports Alibaba official video-synthesis async workflow.")
        self.query_one("#video-guide", Static).update("\n".join(lines))

    def _refresh_speech_guidance(self) -> None:
        task_type = self._select_value(self.query_one("#speech-task", Select))
        model = self._select_value(self.query_one("#speech-model", Select))
        mode = self._select_value(self.query_one("#speech-mode", Select))
        voice = self.query_one("#speech-voice", Input).value.strip()
        prompt = self.query_one("#speech-prompt", TextArea).text.strip()

        errors: List[str] = []
        warnings: List[str] = []
        if not os.getenv("ALIBABA_API_KEY", "").strip():
            errors.append("ALIBABA_API_KEY is missing")
        if not voice:
            errors.append("voice is required")
        if not prompt:
            errors.append("prompt is required")
        if not self._dashscope_sdk_available():
            warnings.append("dashscope SDK not installed (pip install dashscope)")

        lines = [
            f"Flow: provider=alibaba | task={task_type} | model={model}",
            f"Mode: {mode} | Voice: {voice or '(empty)'}",
            f"Audio format: {ALIBABA_SPEECH_AUDIO_FORMAT}",
        ]
        if errors:
            self._set_speech_guide_state("error")
            lines.append(f"ERROR {'; '.join(errors)}")
        elif warnings:
            self._set_speech_guide_state("warn")
            lines.append(f"WARN {'; '.join(warnings)}")
        else:
            self._set_speech_guide_state("ready")
            lines.append("READY Press Enter in prompt box to start speech generation.")
        lines.append("Uses Alibaba realtime TTS session flow.")
        self.query_one("#speech-guide", Static).update("\n".join(lines))

    @staticmethod
    def _dashscope_sdk_available() -> bool:
        return importlib.util.find_spec("dashscope") is not None

    @staticmethod
    def _missing_api_key_env_vars(mode: str, provider: str, provider_b: str) -> List[str]:
        providers = [provider]
        if mode == RUN_MODE_COMPARE and provider_b:
            providers.append(provider_b)
        missing: List[str] = []
        for item in providers:
            key_name = PROVIDER_API_KEY_ENV.get(item)
            if key_name and not os.getenv(key_name, "").strip():
                missing.append(key_name)
        return sorted(set(missing))

    def _collect_generation_inputs(self) -> Dict[str, Any]:
        mode = self._select_value(self.query_one("#gen-mode", Select))
        provider = self._select_value(self.query_one("#gen-provider", Select))
        model = self._select_value(self.query_one("#gen-model", Select))
        task_type = self._select_value(self.query_one("#gen-task", Select))
        prompt = self.query_one("#gen-prompt", TextArea).text.strip()
        provider_b = self._select_value(self.query_one("#gen-provider-b", Select))
        model_b = self._select_value(self.query_one("#gen-model-b", Select))
        prompts_file = self.query_one("#gen-prompts-file", Input).value.strip()
        input_image = self.query_one("#gen-input-image", Input).value.strip() or None
        size = self._selected_generate_size()
        n_raw = self.query_one("#gen-n", Input).value.strip() or "1"
        negative_prompt_enabled = self._negative_prompt_enabled()
        negative_prompt_raw = self.query_one("#gen-negative-prompt", Input).value.strip()
        extra_json = self.query_one("#gen-extra-json", Input).value.strip() or None

        n = int(n_raw)
        if n <= 0:
            raise ValueError("n must be > 0")
        if not model or model == SELECT_NONE_MODEL:
            raise ValueError("Model ID is required")
        if mode in (RUN_MODE_SINGLE, RUN_MODE_COMPARE) and not prompt:
            raise ValueError("prompt is required for single/compare mode")
        if mode == RUN_MODE_COMPARE and (
            not provider_b or not model_b or model_b == SELECT_NONE_MODEL
        ):
            raise ValueError("Provider B and Model B are required in compare mode")
        if mode == RUN_MODE_BATCH and not prompts_file:
            raise ValueError("Prompts file is required in batch mode")
        negative_prompt: Optional[str] = None
        if negative_prompt_enabled:
            if not negative_prompt_raw:
                raise ValueError("negative prompt is required when switch is on")
            negative_prompt = negative_prompt_raw
        self._validate_api_keys(mode, provider, provider_b)

        return {
            "mode": mode,
            "provider": provider,
            "model": model,
            "task_type": task_type,
            "prompt": prompt,
            "provider_b": provider_b,
            "model_b": model_b,
            "prompts_file": prompts_file,
            "input_image": input_image,
            "size": size,
            "n": n,
            "negative_prompt": negative_prompt,
            "extra": read_json_file(extra_json),
        }

    @staticmethod
    def _validate_api_keys(mode: str, provider: str, provider_b: str) -> None:
        providers = [provider]
        if mode == RUN_MODE_COMPARE and provider_b:
            providers.append(provider_b)
        missing_vars: List[str] = []
        for p in providers:
            key_name = PROVIDER_API_KEY_ENV.get(p)
            if key_name and not os.getenv(key_name, "").strip():
                missing_vars.append(key_name)
        if missing_vars:
            names = ", ".join(sorted(set(missing_vars)))
            raise ValueError(f"Missing API key env var(s): {names}")

    def _selected_generate_size(self) -> Optional[str]:
        width = self._select_value(self.query_one("#gen-width", Select))
        height = self._select_value(self.query_one("#gen-height", Select))
        if not (width.isdigit() and height.isdigit()):
            return None
        return f"{width}x{height}"

    def _refresh_generate_model_selects(self) -> None:
        task_type = self._select_value(self.query_one("#gen-task", Select))

        provider_a = self._select_value(self.query_one("#gen-provider", Select))
        model_a = self.query_one("#gen-model", Select)
        options_a = self._build_model_options(provider=provider_a, task_type=task_type)
        model_a.set_options(options_a)
        model_a.value = options_a[0][1] if options_a else SELECT_NONE_MODEL

        provider_b = self._select_value(self.query_one("#gen-provider-b", Select))
        model_b = self.query_one("#gen-model-b", Select)
        options_b = self._build_model_options(provider=provider_b, task_type=task_type)
        model_b.set_options(options_b)
        model_b.value = options_b[0][1] if options_b else SELECT_NONE_MODEL
        self._refresh_generate_size_selects()
        self._refresh_generate_guidance()

    @staticmethod
    def _build_model_options(provider: str, task_type: str) -> List[tuple[str, str]]:
        if not provider:
            return [("No available model", SELECT_NONE_MODEL)]
        entries = list_model_entries(
            provider=provider,
            task_type=task_type,
            recommend_only=False,
        )
        model_ids: List[str] = []
        for item in entries:
            model_id = item["id"]
            if model_id not in model_ids:
                model_ids.append(model_id)
        if not model_ids:
            return [("No available model", SELECT_NONE_MODEL)]
        return [(item, item) for item in model_ids]

    def _refresh_generate_size_selects(self) -> None:
        width_select = self.query_one("#gen-width", Select)
        previous_width = self._select_value(width_select)
        constraints = self._current_size_constraints()
        group = self._select_value(self.query_one("#gen-size-group", Select))
        widths = self._available_width_values(constraints, group)
        if not widths:
            widths = [int(DEFAULT_SIZE_DIMENSION)]
        width_options = [(str(item), str(item)) for item in widths]
        width_select.set_options(width_options)
        if previous_width in {str(item) for item in widths}:
            width_select.value = previous_width
        elif DEFAULT_SIZE_DIMENSION in {str(item) for item in widths}:
            width_select.value = DEFAULT_SIZE_DIMENSION
        else:
            width_select.value = width_options[0][1]
        self._refresh_generate_height_select()

    def _refresh_generate_height_select(self) -> None:
        height_select = self.query_one("#gen-height", Select)
        previous_height = self._select_value(height_select)
        constraints = self._current_size_constraints()
        group = self._select_value(self.query_one("#gen-size-group", Select))
        width = self._select_value(self.query_one("#gen-width", Select))
        if not width.isdigit():
            return
        height_values = self._valid_height_values(constraints, int(width), group)
        if not height_values:
            height_values = [int(DEFAULT_SIZE_DIMENSION)]
        options = [(str(item), str(item)) for item in height_values]
        height_select.set_options(options)
        if previous_height in {str(item) for item in height_values}:
            height_select.value = previous_height
        elif DEFAULT_SIZE_DIMENSION in {str(item) for item in height_values}:
            height_select.value = DEFAULT_SIZE_DIMENSION
        else:
            height_select.value = options[0][1]
        self._update_generate_size_hint()

    def _update_generate_size_hint(self) -> None:
        width = self._select_value(self.query_one("#gen-width", Select))
        height = self._select_value(self.query_one("#gen-height", Select))
        group = self._select_value(self.query_one("#gen-size-group", Select))
        hint = f"Group: {group} | Selected size: unknown"
        if width.isdigit() and height.isdigit():
            pixels = int(width) * int(height)
            hint = f"Group: {group} | Selected size: {width}x{height} ({pixels} px)"
        constraints = self._current_size_constraints()
        min_pixels = constraints.get("min_pixels")
        max_pixels = constraints.get("max_pixels")
        if isinstance(min_pixels, int) and isinstance(max_pixels, int):
            hint += f" | Allowed pixels: {min_pixels}-{max_pixels}"
        self.query_one("#gen-size-hint", Static).update(hint)
        self._refresh_generate_guidance()

    def _current_size_constraints(self) -> Dict[str, Optional[int]]:
        task_type = self._select_value(self.query_one("#gen-task", Select))
        mode = self._select_value(self.query_one("#gen-mode", Select))
        provider = self._select_value(self.query_one("#gen-provider", Select))
        model = self._select_value(self.query_one("#gen-model", Select))
        merged = self._model_size_constraints(provider, model, task_type)
        if mode != RUN_MODE_COMPARE:
            return merged

        provider_b = self._select_value(self.query_one("#gen-provider-b", Select))
        model_b = self._select_value(self.query_one("#gen-model-b", Select))
        second = self._model_size_constraints(provider_b, model_b, task_type)
        return self._merge_constraints(merged, second)

    @staticmethod
    def _model_size_constraints(
        provider: str,
        model: str,
        task_type: str,
    ) -> Dict[str, Optional[int]]:
        constraints: Dict[str, Optional[int]] = {
            "min_width": 512,
            "max_width": 2048,
            "min_height": 512,
            "max_height": 2048,
            "min_pixels": None,
            "max_pixels": None,
        }
        if provider != "alibaba":
            return constraints
        model_l = model.lower()
        if "wan2.6-image" in model_l:
            constraints["min_pixels"] = WAN26_IMAGE_MIN_PIXELS
            constraints["max_pixels"] = WAN26_IMAGE_MAX_PIXELS
            return constraints
        if task_type == TASK_IMAGE2IMAGE:
            constraints["min_width"] = 512
            constraints["max_width"] = 2048
            constraints["min_height"] = 512
            constraints["max_height"] = 2048
        return constraints

    @staticmethod
    def _merge_constraints(
        left: Dict[str, Optional[int]],
        right: Dict[str, Optional[int]],
    ) -> Dict[str, Optional[int]]:
        merged: Dict[str, Optional[int]] = {}
        for key in ("min_width", "min_height", "min_pixels"):
            lv = left.get(key)
            rv = right.get(key)
            if isinstance(lv, int) and isinstance(rv, int):
                merged[key] = max(lv, rv)
            elif isinstance(lv, int):
                merged[key] = lv
            else:
                merged[key] = rv
        for key in ("max_width", "max_height", "max_pixels"):
            lv = left.get(key)
            rv = right.get(key)
            if isinstance(lv, int) and isinstance(rv, int):
                merged[key] = min(lv, rv)
            elif isinstance(lv, int):
                merged[key] = lv
            else:
                merged[key] = rv
        return merged

    @staticmethod
    def _available_width_values(
        constraints: Dict[str, Optional[int]],
        group: str,
    ) -> List[int]:
        results: List[int] = []
        for width in SIZE_DIMENSION_CHOICES:
            if not ImageGenTuiApp._within_bounds(
                width,
                constraints.get("min_width"),
                constraints.get("max_width"),
            ):
                continue
            if ImageGenTuiApp._valid_height_values(constraints, width, group):
                results.append(width)
        return results

    @staticmethod
    def _valid_height_values(
        constraints: Dict[str, Optional[int]],
        width: int,
        group: str,
    ) -> List[int]:
        values: List[int] = []
        for height in SIZE_DIMENSION_CHOICES:
            if not ImageGenTuiApp._within_bounds(
                height,
                constraints.get("min_height"),
                constraints.get("max_height"),
            ):
                continue
            if not ImageGenTuiApp._matches_size_group(width, height, group):
                continue
            pixels = width * height
            if not ImageGenTuiApp._within_bounds(
                pixels,
                constraints.get("min_pixels"),
                constraints.get("max_pixels"),
            ):
                continue
            values.append(height)
        return values

    @staticmethod
    def _matches_size_group(width: int, height: int, group: str) -> bool:
        if group == SIZE_GROUP_SQUARE:
            return width == height
        if group == SIZE_GROUP_LANDSCAPE:
            return width > height
        if group == SIZE_GROUP_PORTRAIT:
            return width < height
        return True

    @staticmethod
    def _within_bounds(
        value: int,
        lower: Optional[int],
        upper: Optional[int],
    ) -> bool:
        if isinstance(lower, int) and value < lower:
            return False
        if isinstance(upper, int) and value > upper:
            return False
        return True

    def _run_generate_mode(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        mode = cast(str, inputs["mode"])
        if mode == RUN_MODE_SINGLE:
            request = self._build_request(
                inputs=inputs,
                provider=cast(str, inputs["provider"]),
                model=cast(str, inputs["model"]),
                prompt=cast(str, inputs["prompt"]),
            )
            run_dir = self._run_single_request(request)
            return {"ok": 1, "failed": 0, "summary": "", "run_dirs": [run_dir]}
        if mode == RUN_MODE_COMPARE:
            return self._run_compare_requests(inputs)
        if mode == RUN_MODE_BATCH:
            return self._run_batch_requests(inputs)
        raise ValueError(f"Unsupported mode: {mode}")

    def _build_request(
        self,
        inputs: Dict[str, Any],
        provider: str,
        model: str,
        prompt: str,
    ) -> GenerationRequest:
        task_type = cast(str, inputs["task_type"])
        input_image = cast(Optional[str], inputs["input_image"])
        supplied_size = cast(Optional[str], inputs["size"])
        negative_prompt = cast(Optional[str], inputs.get("negative_prompt"))
        size = resolve_request_size(task_type, supplied_size, input_image)
        return GenerationRequest(
            provider=provider,
            model=model,
            task_type=task_type,
            prompt=prompt,
            negative_prompt=negative_prompt,
            input_image=input_image,
            size=size,
            n=cast(int, inputs["n"]),
            seed=None,
            extra=cast(Dict[str, Any], inputs["extra"]),
        )

    def _run_single_request(self, request: GenerationRequest) -> str:
        adapters = build_adapters_from_env()
        output_root = ensure_dir(self.output_root)
        response, preprocessed_inputs = run_with_retry_with_artifacts(
            adapter=adapters[request.provider],
            request=request,
            max_retries=int(os.getenv("MAX_RETRIES", "1")),
            retry_delay_seconds=int(os.getenv("RETRY_DELAY_SECONDS", "2")),
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
        return str(run_dir)

    def _run_compare_requests(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        adapters = build_adapters_from_env()
        output_root = ensure_dir(self.output_root)
        max_retries = int(os.getenv("MAX_RETRIES", "1"))
        retry_delay = int(os.getenv("RETRY_DELAY_SECONDS", "2"))
        targets = [
            (cast(str, inputs["provider"]), cast(str, inputs["model"])),
            (cast(str, inputs["provider_b"]), cast(str, inputs["model_b"])),
        ]
        rows: List[Dict[str, str]] = []
        run_dirs: List[str] = []
        for provider, model in targets:
            request = self._build_request(
                inputs=inputs,
                provider=provider,
                model=model,
                prompt=cast(str, inputs["prompt"]),
            )
            try:
                response, preprocessed_inputs = run_with_retry_with_artifacts(
                    adapter=adapters[provider],
                    request=request,
                    max_retries=max_retries,
                    retry_delay_seconds=retry_delay,
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
                run_dirs.append(str(run_dir))
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

        summary = output_root / "compare_summary.csv"
        summarize_results(rows, summary)
        ok = sum(1 for row in rows if row["status"] == "ok")
        return {
            "ok": ok,
            "failed": len(rows) - ok,
            "summary": str(summary),
            "run_dirs": run_dirs,
        }

    def _run_batch_requests(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        adapters = build_adapters_from_env()
        output_root = ensure_dir(self.output_root)
        max_retries = int(os.getenv("MAX_RETRIES", "1"))
        retry_delay = int(os.getenv("RETRY_DELAY_SECONDS", "2"))
        prompts = self._read_prompts_file(cast(str, inputs["prompts_file"]))
        rows: List[Dict[str, str]] = []
        run_dirs: List[str] = []
        provider = cast(str, inputs["provider"])
        model = cast(str, inputs["model"])
        for prompt in prompts:
            request = self._build_request(
                inputs=inputs,
                provider=provider,
                model=model,
                prompt=prompt,
            )
            try:
                response, preprocessed_inputs = run_with_retry_with_artifacts(
                    adapter=adapters[provider],
                    request=request,
                    max_retries=max_retries,
                    retry_delay_seconds=retry_delay,
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
                run_dirs.append(str(run_dir))
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

        summary = output_root / "batch_summary.csv"
        summarize_results(rows, summary)
        ok = sum(1 for row in rows if row["status"] == "ok")
        return {
            "ok": ok,
            "failed": len(rows) - ok,
            "summary": str(summary),
            "run_dirs": run_dirs,
        }

    @staticmethod
    def _read_prompts_file(path: str) -> List[str]:
        prompts = [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines()]
        non_empty = [item for item in prompts if item]
        if not non_empty:
            raise ValueError("prompts file is empty")
        return non_empty

    def _format_generate_result(self, mode: str, payload: Dict[str, Any]) -> str:
        run_dirs = cast(List[str], payload.get("run_dirs", []))
        preview_url = self._first_preview_url(run_dirs)
        preprocessed_status = self._preprocessed_status_line(run_dirs)
        if mode == RUN_MODE_SINGLE:
            if run_dirs:
                message = f"Success. Saved to: {run_dirs[0]}"
                if preview_url:
                    message += f"\nPreview URL (Ctrl+Left Click): {preview_url}"
                if preprocessed_status:
                    message += f"\n{preprocessed_status}"
                return message
            return "Success."
        message = (
            f"Finished mode={mode}: ok={payload.get('ok', 0)} "
            f"failed={payload.get('failed', 0)} summary={payload.get('summary', '')}"
        )
        if preview_url:
            message += f"\nPreview URL (Ctrl+Left Click): {preview_url}"
        if preprocessed_status:
            message += f"\n{preprocessed_status}"
        return message

    def _first_preview_url(self, run_dirs: List[str]) -> str:
        for item in run_dirs:
            preview_url = self._find_preview_url(Path(item))
            if preview_url:
                return preview_url
        return ""

    def _find_preview_url(self, run_dir: Path) -> str:
        exts = {".png", ".jpg", ".jpeg"}
        saved_manifest = run_dir / "saved_images.json"
        if saved_manifest.exists():
            try:
                payload = json.loads(saved_manifest.read_text(encoding="utf-8"))
                saved_files = payload.get("saved_files", [])
                if isinstance(saved_files, list):
                    for raw in saved_files:
                        p = Path(str(raw))
                        if not p.is_absolute():
                            p = run_dir / p
                        if p.suffix.lower() in exts and p.exists():
                            return p.resolve().as_uri()
                        if (
                            p.suffix.lower() == ".txt"
                            and p.name.endswith(".url.txt")
                            and p.exists()
                        ):
                            remote = p.read_text(encoding="utf-8").strip()
                            if remote.startswith("http://") or remote.startswith("https://"):
                                return remote
            except Exception:  # noqa: BLE001
                pass

        images_dir = run_dir / "images"
        if images_dir.exists():
            candidates: List[Path] = []
            for ext in ("*.png", "*.jpg", "*.jpeg"):
                candidates.extend(sorted(images_dir.glob(ext)))
            if candidates:
                return candidates[0].resolve().as_uri()

        response_path = run_dir / "response.json"
        if response_path.exists():
            try:
                response_payload = json.loads(response_path.read_text(encoding="utf-8"))
                images = response_payload.get("images", [])
                if isinstance(images, list):
                    for item in images:
                        if isinstance(item, str) and (
                            item.startswith("http://") or item.startswith("https://")
                        ):
                            return item
            except Exception:  # noqa: BLE001
                pass
        return ""

    def _preprocessed_status_line(self, run_dirs: List[str]) -> str:
        if not run_dirs:
            return ""
        total_files = 0
        run_hits = 0
        for raw in run_dirs:
            count = self._count_preprocessed_inputs(Path(raw))
            if count <= 0:
                continue
            run_hits += 1
            total_files += count
        if total_files <= 0:
            return "Auto-crop input saved: no."
        if len(run_dirs) == 1:
            noun = "file" if total_files == 1 else "files"
            return f"Auto-crop input saved: yes ({total_files} {noun})."
        return f"Auto-crop input saved: yes ({total_files} files across {run_hits} runs)."

    @staticmethod
    def _count_preprocessed_inputs(run_dir: Path) -> int:
        manifest = run_dir / "preprocessed_inputs.json"
        if not manifest.exists():
            return 0
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return 0
        saved_files = payload.get("saved_files", [])
        if not isinstance(saved_files, list):
            return 0
        return len(saved_files)

    def _extract_copy_text(self) -> str:
        focused = self.focused
        if focused is None:
            return ""
        if isinstance(focused, TextArea):
            return focused.text
        if isinstance(focused, Input):
            return focused.value
        if isinstance(focused, DataTable):
            return self._selected_row_text(focused)
        if isinstance(focused, Pretty):
            if self._last_history_detail:
                return json.dumps(self._last_history_detail, ensure_ascii=False, indent=2)
            return str(focused.renderable)
        if isinstance(focused, Static):
            return str(focused.renderable)
        return ""

    @staticmethod
    def _selected_row_text(table: DataTable) -> str:
        row_index = getattr(table, "cursor_row", -1)
        if not isinstance(row_index, int) or row_index < 0:
            return ""
        try:
            row = table.get_row_at(row_index)
        except Exception:  # noqa: BLE001
            return ""
        return "\t".join(str(cell) for cell in row)

    def _selected_models_entry(self) -> Optional[Dict[str, str]]:
        table = self.query_one("#models-table", DataTable)
        row_index = getattr(table, "cursor_row", -1)
        if not isinstance(row_index, int) or row_index < 0:
            return None
        if row_index >= len(self._last_models_entries):
            return None
        return self._last_models_entries[row_index]

    @staticmethod
    def _model_entry_source(entry: Dict[str, str]) -> str:
        if str(entry.get("docs", "")).strip().lower() == "custom":
            return "custom"
        return "built-in"

    def _set_generate_status(self, message: str) -> None:
        self.query_one("#generate-status", Static).update(Text(message))

    def _set_video_status(self, message: str) -> None:
        self.query_one("#video-status", Static).update(Text(message))

    def _set_speech_status(self, message: str) -> None:
        self.query_one("#speech-status", Static).update(Text(message))

    def _set_models_status(self, message: str) -> None:
        self.query_one("#models-status", Static).update(Text(message))

    def _set_config_status(self, message: str) -> None:
        self.query_one("#config-status", Static).update(Text(message))

    def _set_config_guide_state(self, state: str) -> None:
        guide = self.query_one("#config-guide", Static)
        guide.remove_class("guide-error")
        guide.remove_class("guide-warn")
        guide.remove_class("guide-ready")
        if state == "error":
            guide.add_class("guide-error")
            return
        if state == "warn":
            guide.add_class("guide-warn")
            return
        guide.add_class("guide-ready")

    def _refresh_config_guidance(self) -> None:
        values, output_dir, bin_format, persist_preprocessed, auto_crop = (
            self._collect_config_values_unvalidated()
        )
        errors: List[str] = []
        pending = self._pending_config_fields(
            values=values,
            output_dir=output_dir,
            bin_format=bin_format,
            persist_preprocessed=persist_preprocessed,
            auto_crop=auto_crop,
        )

        if not output_dir:
            errors.append("output directory is required")
        else:
            try:
                self._resolve_output_dir(output_dir)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"output directory invalid: {exc}")

        key_total = len(values)
        key_set = sum(1 for value in values.values() if value)
        missing_keys = [name for name, value in values.items() if not value]

        model_id = self.query_one("#conf-model-id", Input).value.strip()
        lines = [
            f"Config file: {self._env_file_path()}",
            f"API keys set: {key_set}/{key_total}",
            f"Current output dir: {self.output_root}",
        ]
        if missing_keys:
            lines.append(f"Missing API keys: {', '.join(missing_keys)}")
        if pending:
            lines.append(f"Pending changes: {', '.join(pending)}")
        else:
            lines.append("Pending changes: none")
        if model_id:
            lines.append("Custom model: ready (press Enter in model ID or click Add Custom Model).")
        else:
            lines.append("Custom model: input model ID to enable Add.")

        if errors:
            self._set_config_guide_state("error")
            lines.append(f"ERROR {'; '.join(errors)}")
        elif pending:
            self._set_config_guide_state("warn")
            lines.append(
                "WARN Changes are not applied yet. Use Apply Session or Save .env + Apply."
            )
        else:
            self._set_config_guide_state("ready")
            lines.append("READY Config is synced with current session.")

        self.query_one("#config-guide", Static).update("\n".join(lines))
        disable_apply_save = bool(errors)
        self.query_one("#conf-apply", Button).disabled = disable_apply_save
        self.query_one("#conf-save", Button).disabled = disable_apply_save
        self.query_one("#conf-add-model", Button).disabled = not bool(model_id)

    def _set_active_output_dir_label(self) -> None:
        self.query_one("#config-output-active", Static).update(
            f"Active output dir: {self.output_root}"
        )

    def _set_generate_controls_disabled(self, disabled: bool) -> None:
        control_ids = [
            "#gen-mode",
            "#gen-provider",
            "#gen-model",
            "#gen-task",
            "#gen-provider-b",
            "#gen-model-b",
            "#gen-prompts-file",
            "#gen-input-image",
            "#gen-size-group",
            "#gen-width",
            "#gen-height",
            "#gen-n",
            "#gen-negative-enabled",
            "#gen-negative-prompt",
            "#gen-extra-json",
            "#gen-prompt",
        ]
        for selector in control_ids:
            widget = self.query_one(selector)
            widget.disabled = disabled

    def _set_video_controls_disabled(self, disabled: bool) -> None:
        control_ids = [
            "#video-task",
            "#video-model",
            "#video-resolution",
            "#video-duration",
            "#video-prompt",
            "#video-input-image",
            "#video-negative-enabled",
            "#video-negative-prompt",
            "#video-extra-json",
        ]
        for selector in control_ids:
            widget = self.query_one(selector)
            widget.disabled = disabled

    def _set_speech_controls_disabled(self, disabled: bool) -> None:
        control_ids = [
            "#speech-task",
            "#speech-model",
            "#speech-mode",
            "#speech-voice",
            "#speech-prompt",
            "#speech-extra-json",
        ]
        for selector in control_ids:
            widget = self.query_one(selector)
            widget.disabled = disabled

    @staticmethod
    def _copy_to_clipboard(text: str) -> None:
        if os.name == "nt":
            subprocess.run(["clip"], input=text.encode("utf-16le"), check=True)
            return
        if shutil.which("pbcopy"):
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
            return
        if shutil.which("xclip"):
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text.encode("utf-8"),
                check=True,
            )
            return
        if shutil.which("xsel"):
            subprocess.run(
                ["xsel", "--clipboard", "--input"],
                input=text.encode("utf-8"),
                check=True,
            )
            return
        raise RuntimeError("No clipboard command found (clip/pbcopy/xclip/xsel).")

    def _attach_generate_log_handler(self) -> None:
        if self._generate_log_handler is not None:
            return

        app = self

        class _TuiLogHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                message = self.format(record)
                app._generate_latest_log = message

        handler = _TuiLogHandler()
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logging.getLogger().addHandler(handler)
        image_logger = logging.getLogger("image_gen_test_tool")
        self._generate_log_prev_level = image_logger.level
        image_logger.setLevel(logging.INFO)
        self._generate_log_handler = handler

    def _detach_generate_log_handler(self) -> None:
        if self._generate_log_handler is None:
            return
        logging.getLogger().removeHandler(self._generate_log_handler)
        self._generate_log_handler = None
        if self._generate_log_prev_level is not None:
            logging.getLogger("image_gen_test_tool").setLevel(self._generate_log_prev_level)
            self._generate_log_prev_level = None

    def _sync_prompt_height(self) -> None:
        self._sync_textarea_height("#gen-prompt")

    def _sync_video_prompt_height(self) -> None:
        self._sync_textarea_height("#video-prompt")

    def _sync_speech_prompt_height(self) -> None:
        self._sync_textarea_height("#speech-prompt")

    def _sync_textarea_height(self, selector: str) -> None:
        with contextlib.suppress(Exception):
            prompt = self.query_one(selector, TextArea)
            terminal_half = max(6, self.size.height // 2)
            width = max(20, prompt.size.width if prompt.size.width > 0 else self.size.width - 6)
            text = prompt.text or ""
            logical_lines = text.splitlines() or [""]
            visual_lines = 0
            for line in logical_lines:
                visual_lines += max(1, (len(line) // max(10, width - 2)) + 1)
            target_height = min(max(3, visual_lines + 1), terminal_half)
            prompt.styles.height = target_height

    def _load_config_inputs_from_env(self) -> None:
        env_output_dir = os.getenv(OUTPUT_DIR_ENV, str(self.output_root))
        self.query_one("#conf-output-dir", Input).value = env_output_dir
        bin_format = self._normalize_bin_format(os.getenv(BIN_ALIAS_FORMAT_ENV, "png"))
        self.query_one("#conf-bin-format", Select).value = bin_format
        persist_preprocessed = self._normalize_on_off(
            os.getenv(PERSIST_PREPROCESSED_INPUT_ENV, PERSIST_PREPROCESSED_INPUT_DEFAULT),
            default=PERSIST_PREPROCESSED_INPUT_DEFAULT,
        )
        self.query_one("#conf-persist-preprocessed", Select).value = persist_preprocessed
        auto_crop = self._normalize_on_off(
            os.getenv(ALIBABA_AUTOCROP_ENV, AUTOCROP_DEFAULT),
            default=AUTOCROP_DEFAULT,
        )
        self.query_one("#conf-autocrop", Select).value = auto_crop
        for env_name, input_id in API_KEY_FIELDS:
            value = os.getenv(env_name, "")
            self.query_one(f"#{input_id}", Input).value = value
        self._set_active_output_dir_label()

    def _collect_config_values_unvalidated(self) -> tuple[Dict[str, str], str, str, str, str]:
        values: Dict[str, str] = {}
        for env_name, input_id in API_KEY_FIELDS:
            values[env_name] = self.query_one(f"#{input_id}", Input).value.strip()
        output_dir = self.query_one("#conf-output-dir", Input).value.strip()
        bin_format = self._normalize_bin_format(
            self._select_value(self.query_one("#conf-bin-format", Select))
        )
        persist_preprocessed = self._normalize_on_off(
            self._select_value(self.query_one("#conf-persist-preprocessed", Select)),
            default=PERSIST_PREPROCESSED_INPUT_DEFAULT,
        )
        auto_crop = self._normalize_on_off(
            self._select_value(self.query_one("#conf-autocrop", Select)),
            default=AUTOCROP_DEFAULT,
        )
        return values, output_dir, bin_format, persist_preprocessed, auto_crop

    def _pending_config_fields(
        self,
        values: Dict[str, str],
        output_dir: str,
        bin_format: str,
        persist_preprocessed: str,
        auto_crop: str,
    ) -> List[str]:
        pending: List[str] = []
        if output_dir:
            form_output = str(self._resolve_output_dir(output_dir))
            runtime_output = str(
                self._resolve_output_dir(os.getenv(OUTPUT_DIR_ENV, str(self.output_root)))
            )
            if form_output != runtime_output:
                pending.append("output_dir")
        runtime_bin = self._normalize_bin_format(os.getenv(BIN_ALIAS_FORMAT_ENV, "png"))
        if bin_format != runtime_bin:
            pending.append("bin_alias_format")
        runtime_persist = self._normalize_on_off(
            os.getenv(PERSIST_PREPROCESSED_INPUT_ENV, PERSIST_PREPROCESSED_INPUT_DEFAULT),
            default=PERSIST_PREPROCESSED_INPUT_DEFAULT,
        )
        if persist_preprocessed != runtime_persist:
            pending.append("persist_preprocessed_input")
        runtime_autocrop = self._normalize_on_off(
            os.getenv(ALIBABA_AUTOCROP_ENV, AUTOCROP_DEFAULT),
            default=AUTOCROP_DEFAULT,
        )
        if auto_crop != runtime_autocrop:
            pending.append("alibaba_autocrop")
        for env_name, form_value in values.items():
            if form_value != os.getenv(env_name, "").strip():
                pending.append(env_name)
        return pending

    def _collect_config_values(self) -> tuple[Dict[str, str], str, str, str, str]:
        values, output_dir, bin_format, persist_preprocessed, auto_crop = (
            self._collect_config_values_unvalidated()
        )
        if not output_dir:
            raise ValueError("Output directory is required")
        if bin_format not in {"png", "jpg"}:
            raise ValueError("Default bin format must be png or jpg")
        if persist_preprocessed not in {"on", "off"}:
            raise ValueError("Persist auto-crop input must be on or off")
        if auto_crop not in {"on", "off"}:
            raise ValueError("Alibaba auto-crop must be on or off")
        return values, output_dir, bin_format, persist_preprocessed, auto_crop

    @staticmethod
    def _normalize_bin_format(raw: str) -> str:
        text = raw.strip().lower()
        if text == "jpeg":
            return "jpg"
        if text not in {"png", "jpg"}:
            return "png"
        return text

    @staticmethod
    def _normalize_on_off(raw: str, default: str) -> str:
        text = raw.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return "on"
        if text in {"0", "false", "no", "off"}:
            return "off"
        return default

    @staticmethod
    def _apply_api_key_values(values: Dict[str, str]) -> None:
        for key, value in values.items():
            os.environ[key] = value

    def _save_config_to_env(
        self,
        values: Dict[str, str],
        output_dir: Path,
        bin_format: str,
        persist_preprocessed: str,
        auto_crop: str,
    ) -> None:
        env_path = self._env_file_path()
        env_path.touch(exist_ok=True)
        set_key(str(env_path), OUTPUT_DIR_ENV, str(output_dir))
        set_key(str(env_path), BIN_ALIAS_FORMAT_ENV, bin_format)
        set_key(str(env_path), PERSIST_PREPROCESSED_INPUT_ENV, persist_preprocessed)
        set_key(str(env_path), ALIBABA_AUTOCROP_ENV, auto_crop)
        for key, value in values.items():
            set_key(str(env_path), key, value)

    @staticmethod
    def _env_file_path() -> Path:
        return Path.cwd() / ".env"

    @staticmethod
    def _resolve_output_dir(value: str) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path

    def _apply_output_dir(self, output_dir: str) -> Path:
        resolved = self._resolve_output_dir(output_dir)
        ensure_dir(resolved)
        self.output_root = resolved
        self._set_active_output_dir_label()
        self._refresh_history_table()
        return resolved

    @staticmethod
    def _apply_bin_alias_format(bin_format: str) -> None:
        os.environ[BIN_ALIAS_FORMAT_ENV] = bin_format

    @staticmethod
    def _apply_persist_preprocessed_input(persist_preprocessed: str) -> None:
        os.environ[PERSIST_PREPROCESSED_INPUT_ENV] = persist_preprocessed

    @staticmethod
    def _apply_alibaba_autocrop(auto_crop: str) -> None:
        os.environ[ALIBABA_AUTOCROP_ENV] = auto_crop

    def _refresh_models_table(self) -> None:
        table = self.query_one("#models-table", DataTable)
        table.clear(columns=True)
        table.add_columns("provider", "model_id", "tasks", "status", "source")
        entries = list_model_entries(
            provider=self._optional_select_value(self.query_one("#models-provider", Select)),
            task_type=self._optional_select_value(self.query_one("#models-task", Select)),
            recommend_only=self._select_value(self.query_one("#models-recommend", Select))
            == "recommended",
        )
        self._last_models_entries = entries
        for row in entries:
            table.add_row(
                row["provider"],
                row["id"],
                row["tasks"],
                row["status"],
                self._model_entry_source(row),
            )

    def _refresh_history_table(self) -> None:
        table = self.query_one("#history-table", DataTable)
        table.clear(columns=True)
        table.add_columns("run_id", "provider", "model", "task_type", "images")
        entries = list_history_entries(
            output_root=self.output_root,
            provider=self._optional_select_value(self.query_one("#history-provider", Select)),
            limit=self._parse_limit(self.query_one("#history-limit", Input).value.strip()),
        )
        for row in entries:
            table.add_row(
                cast(str, row["run_id"]),
                cast(str, row["provider"]),
                cast(str, row["model"]),
                cast(str, row["task_type"]),
                str(row["images"]),
            )

    def _resolve_history_run(self, run_id: str) -> Path:
        run_path = Path(run_id)
        if run_path.exists() and run_path.is_dir():
            return run_path
        return self.output_root / run_id

    @staticmethod
    def _parse_limit(value: str) -> int:
        if not value:
            return 20
        parsed = int(value)
        if parsed <= 0:
            raise ValueError("limit must be > 0")
        return parsed

    @staticmethod
    def _select_value(select: Select[str]) -> str:
        value = select.value
        if value is None or not isinstance(value, str):
            return ""
        return value

    @staticmethod
    def _optional_select_value(select: Select[str]) -> Optional[str]:
        value = ImageGenTuiApp._select_value(select)
        if value in {SELECT_ALL, SELECT_UNSET, SELECT_NONE_MODEL, ""}:
            return None
        return value


def run_tui_app(output_dir: Optional[str] = None) -> None:
    load_dotenv()
    resolved_output_dir = output_dir or os.getenv(OUTPUT_DIR_ENV, "runs")
    app = ImageGenTuiApp(output_dir=resolved_output_dir)
    app.run()
