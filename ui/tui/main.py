def run() -> None:
    try:
        from ui.tui.app import run_tui_app
    except ModuleNotFoundError as exc:
        if exc.name == "textual":
            raise SystemExit(
                "textual is not installed. Run: pip install -e .[tui]"
            ) from exc
        raise
    run_tui_app()
