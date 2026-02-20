# TUI/GUI Roadmap

## Goal
Build UI capabilities without duplicating provider logic. Keep `cli.py`, TUI, and future GUI on top of the same service layer.

## Architecture Boundary
- `core/services/`: business services, no argparse dependency.
- `cli.py`: command parsing + console rendering only.
- `ui/tui/`: Textual app calling `core/services`.
- `ui/gui/` (optional later): desktop shell calling `core/services`.

## Milestones
### M0 (Done)
- Introduce reusable service modules:
  - `core/services/catalog.py`
  - `core/services/history.py`
  - `core/services/generation.py`
- Keep CLI behavior unchanged by delegating logic to services.
- Ensure packaging includes `core.services`.

### M1 (TUI MVP, Initial Version Done)
- Framework: Textual.
- Views:
  - Generate (`single`, `compare`, `batch`)
  - Models (`provider/task/recommend` filters)
  - History (`list/show`)
- Non-blocking run execution with visible progress and final status.

Current gap to complete M1:
- Improve visual feedback for long-running batch/compare operations.

### M2 (Stability + UX)
- Unified error surface for provider/API errors.
- Add failed-run persistence for all command paths.
- Add config panel support (`.env` preview + validation hints).

### M3 (Optional GUI)
- Pick one:
  - Flet: quicker cross-platform shell
  - PySide6: richer native desktop control
- Start with 2 pages only: Generate + History.

## Acceptance Criteria (Per Milestone)
- Existing CLI tests remain green.
- New UI layer uses only `core/services`, not adapter internals.
- No provider-specific payload logic duplicated outside `adapters/`.
