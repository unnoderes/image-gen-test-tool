# Changelog

All notable changes to this project are documented in this file.

## [0.1.0] - 2026-02-19

### Added
- Standard Python CLI packaging via `pyproject.toml` and `setuptools` backend.
- Executable commands through `console_scripts`: `image-gen-test` and `igt`.
- CLI version flag: `--version`.
- Global verbosity flags: `--verbose` and `--quiet`.
- Basic `setup.py` shim for compatibility with tooling workflows.
- Build tooling dependency (`build`) for generating wheel/sdist artifacts.

### Changed
- README now documents install-as-CLI usage and packaging/release commands.

