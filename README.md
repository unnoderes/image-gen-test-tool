# Image Generation API Test Tool (Minimal)

This is a minimal test harness for image generation APIs.

Current scope:
- Providers: Alibaba, Google, GLM
- Tasks: `text_to_image`, `image_to_image`
- Commands: `single`, `compare`, `batch`, `models`, `history`
- Output persistence: every run writes request, response, and saved images to disk
- Validation: `pydantic v2`
- Shared service layer for CLI/TUI/GUI reuse: `core/services/`
- Documentation: `docs/AGENTS.md`, `docs/CHANGELOG.md`, `docs/tui-gui-roadmap.md`
- Quick start guide: `docs/guides/quick-start-windows.txt`

## 1. Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

After install, use CLI commands directly:

```bash
image-gen-test --help
igt --help
```

For development (tests + lint):

```bash
pip install -e .[dev]
```

For TUI:

```bash
pip install -e .[tui]
igt-tui
```

Global output controls:

```bash
image-gen-test --verbose --help
image-gen-test --quiet --help
```

Copy and edit environment variables:

```bash
copy .env.example .env
```

Fill these fields in `.env`:
- `ALIBABA_API_KEY`
- `ALIBABA_REGION` (`intl` or `cn`)
- `GOOGLE_API_KEY`
- `GLM_API_KEY`

Optional fields:
- `ALIBABA_ASYNC=true` enables task polling mode
- `ALIBABA_TEXT2IMAGE_URL` / `ALIBABA_IMAGE2IMAGE_URL` for custom endpoints
- `ALIBABA_VIDEO_URL` for Alibaba video endpoint override
- `ALIBABA_SPEECH_WS_URL` for Alibaba speech realtime websocket override
- `GOOGLE_TEXT2IMAGE_URL` / `GOOGLE_IMAGE2IMAGE_URL` for custom endpoints
- `GLM_BASE_URL` / `GLM_TEXT2IMAGE_URL` / `GLM_IMAGE2IMAGE_URL` for custom endpoints
- `IGT_OUTPUT_DIR` custom default output directory (used by generation + history)
- `IGT_BIN_ALIAS_FORMAT` default alias format for downloaded `.bin` files (`png` or `jpg`, default `png`)
- `IGT_ALIBABA_IMAGE2IMAGE_AUTOCROP` enable/disable Alibaba image editing auto-crop (`on` / `off`, default `off`)
- `IGT_PERSIST_PREPROCESSED_INPUT` persist auto-cropped source image for Alibaba image editing (`on` / `off`, default `off`)
- `IGT_CUSTOM_MODELS_PATH` custom model registry file path (default `./custom_models.json`)

Notes:
- Default Alibaba endpoint: DashScope multimodal generation.
- Default Google endpoint: Gemini API `models/{model}:generateContent`.
- If your model family has different payload requirements, only modify adapter mapping.

Recommended starter models:
- Alibaba: `qwen-image-max`
- Google: `gemini-2.5-flash-image`
- GLM: `cogview-4-250304` or `glm-image`

## 2. Single Request

```bash
image-gen-test single ^
  --provider alibaba ^
  --model qwen-image-max ^
  --task-type text_to_image ^
  --prompt "A cozy wooden cabin in snow" ^
  --size 1024x1024 ^
  --n 1
```

For `image_to_image`, add `--input-image`:

```bash
image-gen-test single ^
  --provider google ^
  --model gemini-2.5-flash-image ^
  --task-type image_to_image ^
  --prompt "Turn this photo into anime style" ^
  --input-image "C:\path\to\input.png"
```

`image_to_image` size behavior:
- If `--size` is provided, that size is used.
- If `--size` is omitted, the tool auto-detects source image size and sends it.
- For Alibaba `image_to_image`, MVP auto-crop is disabled by default.
- Enable auto-crop with `--auto-crop on` or `IGT_ALIBABA_IMAGE2IMAGE_AUTOCROP=on` (center crop + resize into `[512, 2048]`).
- Add global option `--persist-preprocessed-input on` to persist auto-cropped source files per run.
- Negative prompt is disabled by default.
- Enable it with `--negative-prompt-enabled on --negative-prompt "..."`.

GLM text-to-image example:

```bash
image-gen-test single ^
  --provider glm ^
  --model cogview-4-250304 ^
  --task-type text_to_image ^
  --prompt "A futuristic city skyline at sunset"
```

## 3. Compare Alibaba vs Google

```bash
image-gen-test compare ^
  --prompt "A red sports car drifting on wet road" ^
  --task-type text_to_image ^
  --model-alibaba qwen-image-max ^
  --model-google gemini-2.5-flash-image
```

This writes `compare_summary.csv` in the output directory.

## 4. Batch Test

Prepare a prompts file (one prompt per line), then run:

```bash
image-gen-test batch ^
  --provider glm ^
  --model your_model ^
  --task-type text_to_image ^
  --prompts-file prompts.txt
```

This writes `batch_summary.csv` in the output directory.

## 5. Built-in Model Catalog

Use CLI to query hardcoded official model IDs quickly:

```bash
igt models
igt models --provider alibaba
igt models --recommend
igt models --provider alibaba --task-type image_to_image
igt models --format json
```

Notes:
- This catalog is curated and versioned in code for fast lookup.
- `--recommend` keeps only recommended models from the built-in catalog.
- `--task-type` helps narrow to callable models for a specific task.
- Always verify final availability against provider docs.

## 6. History Query

Inspect saved runs from `--output-dir` (default `runs/`):

```bash
igt history list --limit 10
igt history show --run-id 20260219-120301_alibaba_text_to_image_req_abc
```

Useful options:
- `igt history list --provider alibaba`
- `igt history list --format json`
- `igt history show --run-id <folder_name_or_full_path> --format json`

## 7. Output Layout

Default output root is `runs/`.

Each run creates a folder:

```
runs/{timestamp}_{provider}_{task_type}_{request_id}/
  request.json
  response.json
  saved_images.json
  images/
  preprocessed_inputs.json   # optional, when auto-crop persistence is enabled
  preprocessed_inputs/       # optional, saved auto-cropped source images
```

## 8. Extra Payload Overrides

If a model needs custom fields, place JSON in a file and pass `--extra-json`:

```json
{
  "parameters": {
    "style": "photorealistic"
  }
}
```

Example:

```bash
image-gen-test single ... --extra-json extra.json
```

## 9. Run Tests and Lint

```bash
pytest -q
ruff check .
```

Version:

```bash
image-gen-test --version
```

## 10. Build Release Artifacts

Build wheel and source distribution:

```bash
python -m pip install -e .[release]
python -m build
```

Artifacts will be generated in `dist/`:
- `*.whl`
- `*.tar.gz`

## 11. TUI MVP

Command:

```bash
igt-tui
```

Current tabs:
- `Generate`: run `single`, `compare`, and `batch` workflows.
- `Video`: run Alibaba video API tests (`text_to_video` / `image_to_video`).
- `Speech`: run Alibaba speech realtime API tests (`text_to_speech`).
- `Models`: browse built-in/custom model catalog, with custom model deletion.
- `History`: list saved runs and inspect run details.
- `Config`: manage provider API keys in TUI.

Generate tab notes:
- Inputs auto show/hide by mode (single/compare/batch) to reduce invalid combinations.
- Model ID selectors are dropdowns and auto-refresh based on selected provider/task.
- Size uses width/height dropdowns (limited options) instead of free-text size input.
- Size group dropdown added: `All` / `Square` / `Landscape` / `Portrait`.
- Width/height options are linked and filtered by active model constraints.
- When required provider API keys are missing, UI shows direct env-var hints.
- Generation runs in background; other tabs remain interactive during execution.
- Prompt box is anchored at the bottom of Generate tab.
- Press `Enter` in Prompt box to run current mode (`single/compare/batch`).
- Prompt box auto-wraps and auto-resizes up to half of terminal height.
- Press `Ctrl+J` in Prompt box for manual newline.
- Press `Ctrl+C` in TUI to copy focused content (input value, selected table row, or history detail).
- After success, status card shows a `file://` preview URL for generated `.png/.jpg` (Ctrl+Left Click to open).
- Negative prompt input is behind a manual switch (`off` by default).

Video tab notes:
- Provider is fixed to Alibaba API structure.
- Supported tasks: `text_to_video` and `image_to_video`.
- Default model is fixed: `wan2.6-i2v-flash`.
- Uses Alibaba async workflow (`video-synthesis` create + task polling) and saves results into `runs/.../videos/`.
- `image_to_video` requires input image path/URL.
- Negative prompt is optional and behind a manual switch (`off` by default).

Speech tab notes:
- Provider is fixed to Alibaba API structure.
- Task is fixed to `text_to_speech`.
- Default model is fixed: `qwen3-tts-vd-realtime-2026-01-15`.
- Uses Alibaba realtime websocket session flow and saves outputs into `runs/.../audios/`.
- Requires `dashscope` SDK in runtime environment (`pip install dashscope`).
- `Voice` and `Prompt` are required fields.

Models tab notes:
- Supports provider/task/status filters.
- Table includes `source` (`built-in` / `custom`) for each model row.
- `Delete Selected` only removes `custom` models; built-in models are protected.

Config tab notes:
- `Load Current Env`: load values from current process environment.
- `Apply Session`: apply API keys, output directory, bin alias format, auto-crop enablement, and auto-crop persistence to current TUI session only.
- `Save .env + Apply`: write API keys, `IGT_OUTPUT_DIR`, `IGT_BIN_ALIAS_FORMAT`, `IGT_ALIBABA_IMAGE2IMAGE_AUTOCROP`, and `IGT_PERSIST_PREPROCESSED_INPUT` into `.env`.
- Config guide card now shows realtime `ERROR/WARN/READY`, missing keys, and pending unapplied changes.
- `Output directory` is shared by generation outputs and History tab queries.
- Downloaded URL images still keep original `.bin`; tool also writes a same-directory alias file as `.png` or `.jpg`.
- `Custom Model Registration` allows adding model IDs under existing providers only:
  - Provider: fixed choices (`alibaba` / `google` / `glm`)
  - Model ID: required
  - Task type (`text_to_image` / `image_to_image`): required
  - Recommended flag: optional
  - Press `Enter` inside `Model ID` input to add quickly (same as `Add Custom Model` button).
