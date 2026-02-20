# Image Generation API Test Tool

[中文文档](README.zh-CN.md)

A minimal test tool for generation APIs, with both CLI and TUI.

## Scope

- Providers: `alibaba`, `google`, `glm`
- Image tasks: `text_to_image`, `image_to_image`
- CLI commands: `single`, `compare`, `batch`, `models`, `history`
- TUI tabs: `Generate`, `Video`, `Speech`, `Models`, `History`, `Config`
- Shared service layer: `core/services/`

## Requirements

- Python `>=3.11`

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

Optional extras:

```bash
pip install -e .[dev]   # pytest + ruff + build
pip install -e .[tui]   # textual
```

Entrypoints:

```bash
igt --help
image-gen-test --help
igt-tui
```

## Environment Setup

Copy template:

```bash
copy .env.example .env
```

Common keys:

- `ALIBABA_API_KEY`
- `ALIBABA_REGION` (`intl` or `cn`)
- `GOOGLE_API_KEY`
- `GLM_API_KEY`

Useful optional vars:

- `IGT_OUTPUT_DIR`: default output root
- `IGT_BIN_ALIAS_FORMAT`: alias format for downloaded `.bin` (`png` or `jpg`)
- `IGT_ALIBABA_IMAGE2IMAGE_AUTOCROP`: `on` / `off` (default `off`)
- `IGT_PERSIST_PREPROCESSED_INPUT`: persist auto-cropped source (`on` / `off`, default `off`)
- `IGT_CUSTOM_MODELS_PATH`: custom model registry JSON path

## CLI Quick Start

### Single

```bash
igt single --provider alibaba --model qwen-image-max --task-type text_to_image --prompt "A cozy wooden cabin in snow" --size 1024x1024 --n 1
```

Image edit:

```bash
igt single --provider google --model gemini-2.5-flash-image --task-type image_to_image --prompt "Turn this photo into anime style" --input-image "C:\path\to\input.png"
```

Notes:

- `image_to_image` requires `--input-image`.
- If `--size` is omitted for `image_to_image`, source image size is auto-used when available.
- Negative prompt is off by default. Enable with:
  - `--negative-prompt-enabled on --negative-prompt "..."`
- Alibaba auto-crop is off by default. Enable with:
  - `--auto-crop on`
- Persist auto-cropped input with:
  - `--persist-preprocessed-input on`

### Compare

```bash
igt compare --prompt "A red sports car drifting on wet road" --task-type text_to_image --provider-a alibaba --model-a qwen-image-max --provider-b google --model-b gemini-2.5-flash-image
```

Output includes `compare_summary.csv`.

### Batch

```bash
igt batch --provider glm --model cogview-4-250304 --task-type text_to_image --prompts-file prompts.txt
```

Output includes `batch_summary.csv`.

### Models Catalog

```bash
igt models
igt models --provider alibaba
igt models --provider alibaba --task-type image_to_image
igt models --recommend
igt models --format json
```

### History

```bash
igt history list --limit 10
igt history show --run-id 20260219-120301_alibaba_text_to_image_req_abc
```

## TUI (`igt-tui`)

### Generate tab

- Modes: `single`, `compare`, `batch`
- Model dropdowns are filtered by provider/task
- Width/height are constrained dropdowns
- Prompt box is anchored at bottom
- Prompt shortcuts:
  - `Enter`: run current mode
  - `Ctrl+J`: newline
- Prompt auto-wraps and auto-resizes up to half terminal height
- `Ctrl+C` copies focused content

### Video tab (Alibaba)

- Tasks: `text_to_video`, `image_to_video`
- Default model: `wan2.6-i2v-flash`
- Uses Alibaba async video workflow
- `image_to_video` requires input image path/URL
- Negative prompt is optional and switch-controlled
- Prompt input behavior matches Generate tab (bottom box, `Enter` submit, `Ctrl+J` newline)

### Speech tab (Alibaba)

- Task: `text_to_speech`
- Default model: `qwen3-tts-vd-realtime-2026-01-15`
- Uses Alibaba realtime websocket flow
- Runtime dependency: `dashscope` (`pip install dashscope`)
- Required fields: `voice`, `prompt`
- Prompt input behavior matches Generate tab (bottom box, `Enter` submit, `Ctrl+J` newline)

### Models tab

- Filter by provider/task/recommendation
- Built-in and custom model entries are shown
- Delete supports custom models only
- Press `Delete` on selected custom row for quick removal

### History tab

- List saved runs
- Inspect details by run id/path

### Config tab

- Manage API keys and runtime config in TUI
- `Load Current Env`, `Apply Session`, `Save .env + Apply`
- Controls include:
  - output directory
  - bin alias format (`png` / `jpg`)
  - Alibaba auto-crop switch
  - auto-cropped input persistence switch
  - custom model registration under existing providers

## Output Layout

Default root: `runs/`

```text
runs/{timestamp}_{provider}_{task_type}_{request_id}/
  request.json
  response.json
  saved_images.json
  images/
  preprocessed_inputs.json   # optional
  preprocessed_inputs/       # optional
```

Video outputs are stored under `videos/`, speech outputs under `audios/` in run folders.

## Development

```bash
pytest -q
ruff check .
```

Build artifacts:

```bash
python -m pip install -e .[release]
python -m build
```

