# Repository Guidelines

## Project Structure & Module Organization
- `cli.py`: CLI entrypoint and command orchestration (`single`, `compare`, `batch`, `models`, `history`).
- `adapters/`: provider mappings (`alibaba.py`, `google.py`, `glm.py`).
- `core/`: shared request/response models and helpers.
- `core/services/`: reusable business services for catalog, history, and generation settings.
- `ui/tui/`: Textual TUI frontend (`igt-tui` entrypoint).
- `docs/tui-gui-roadmap.md`: staged UI development plan (TUI first, GUI optional).
- `tests/`: unit tests for adapters, CLI argument behavior, and IO/size logic.
- Runtime artifacts: `runs/<timestamp>_.../` with request/response/images.

## Build, Test, and Development Commands
- Python requirement: `>=3.11`.
- Install CLI: `pip install -e .`
- Install dev dependencies: `pip install -e .[dev]`
- Install TUI dependencies: `pip install -e .[tui]`
- Help: `igt --help`
- Run TUI: `igt-tui`
- Test: `pytest -q`
- Lint: `ruff check .`
- Build artifacts: `python -m build` (outputs in `dist/`).

## Coding Style & Naming Conventions
- Python, 4-space indentation, UTF-8, line length <= 100 (`ruff`).
- Keep boundaries strict: adapter-specific payloads in `adapters/`, cross-provider logic in `core/`.
- Naming: files/functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`.
- Prefer small explicit functions; avoid hidden side effects.

## Testing Guidelines
- Framework: `pytest` (+ `requests-mock` for HTTP behavior).
- Test file naming: `tests/test_*.py`.
- Add tests for any new provider mapping, CLI mode, or size/format behavior.
- Required before merge: `ruff check .` and `pytest -q` both pass.

## Commit & Pull Request Guidelines
- Git history is not available in this snapshot; use Conventional Commits:
  - `feat: ...`, `fix: ...`, `docs: ...`, `refactor: ...`, `test: ...`
- Keep commits scoped to one intent.
- PRs should include: summary, changed modules, `ruff`/`pytest` output, and CLI examples if behavior changed.

## CLI Behavior Notes
- Global flags must appear before subcommand (example: `igt --quiet single ...`).
- `models` provides a curated, hardcoded provider catalog:
  - `igt models --provider alibaba --task-type image_to_image`
  - `igt models --recommend`
  - `igt models --format json`
- `history` inspects saved run artifacts:
  - `igt history list --limit 10`
  - `igt history show --run-id <run_folder_name>`
- `compare` supports:
  - new mode: `--provider-a --model-a --provider-b --model-b`
  - legacy mode: `--model-alibaba --model-google`
  Do not mix both modes in one command.
- For `image_to_image`, omitted `--size` auto-uses source image size when detectable.
- Alibaba image editing enforces width/height in `[512, 2048]`.
- Alibaba MVP auto-crop (center crop + resize) runs only when explicitly enabled.
- Alibaba auto-crop is configurable via `IGT_ALIBABA_IMAGE2IMAGE_AUTOCROP` (`off` by default) or CLI `--auto-crop on|off`.
- Auto-cropped source images are temporary by default; enable persistence via `IGT_PERSIST_PREPROCESSED_INPUT=on` or CLI `--persist-preprocessed-input on`.
- Negative prompt is opt-in:
  - CLI: `--negative-prompt-enabled on --negative-prompt "..."`
  - default is off

## TUI Behavior Notes
- Generate tab supports `single`, `compare`, and `batch` modes.
- Video tab supports Alibaba video API testing (`text_to_video` / `image_to_video`) with fixed default model `wan2.6-i2v-flash`.
- Speech tab supports Alibaba realtime TTS API testing (`text_to_speech`) with fixed default model `qwen3-tts-vd-realtime-2026-01-15`.
- Prompt input is a single bottom `TextArea` in Generate tab.
- Prompt shortcuts:
  - `Enter`: submit current mode.
  - `Ctrl+J`: insert newline in prompt.
- Generate tab supports negative prompt switch + input:
  - default switch state is off
  - when on, negative prompt input is required before run
- Video tab supports negative prompt switch + input:
  - default switch state is off
  - when on, negative prompt input is required before run
- Speech tab uses explicit form inputs:
  - required: `voice`, `prompt`
  - mode options: `server_commit`, `commit`
  - runtime requires `dashscope` SDK and `ALIBABA_API_KEY`
- Textual event wiring:
  - For custom `Message` classes without `control`, use `@on(MyMessage)` without selector.
- Config tab supports API key management:
  - output directory field (shared by generation + history)
  - default bin alias format (`png` / `jpg`) for downloaded URL images
  - Alibaba auto-crop switch (`IGT_ALIBABA_IMAGE2IMAGE_AUTOCROP`: `on` / `off`)
  - auto-crop source persistence switch (`IGT_PERSIST_PREPROCESSED_INPUT`: `on` / `off`)
  - custom model registration under existing providers only (`alibaba` / `google` / `glm`)
  - custom model task type is required (`text_to_image` / `image_to_image`)
  - custom model recommended flag is optional
  - `Load Current Env`
  - `Apply Session`
  - `Save .env + Apply` (writes to `.env` under current working directory)
- Config guide card behavior:
  - shows realtime `ERROR` / `WARN` / `READY` state
  - shows missing API keys and pending unapplied fields
  - disables `Apply Session` and `Save .env + Apply` when config is invalid
  - supports quick add: press `Enter` in `Custom model ID` to trigger `Add Custom Model`
- Models tab supports deleting selected custom model rows:
  - built-in rows are protected and cannot be deleted
  - custom rows are identified by `source=custom`
  - supports keyboard delete: focus `Models` table and press `Delete` to remove selected custom row (no confirmation)
- Global copy shortcut:
  - `Ctrl+C`: copy focused content (input value, selected table row, or history detail JSON).
- If required provider API keys are missing, Generate validation should surface env-var names directly.

## Security & Configuration Tips
- Keep secrets only in `.env`; never hardcode API keys.
- Validate with `.env.example` when adding new provider options.
- Preserve CLI backward compatibility where practical; document breaking changes.
