# Repository Guidelines

## Project Structure & Module Organization
`enigmatic_dgb/` holds the core Python package (CLI, console, encoder/decoder,
planner, ordinals). `enigmatic_dgb/ordinals/` contains Taproot tooling. `tests/`
is the pytest suite. `docs/` and `specs/` store design notes and protocol
specifications. `examples/` contains dialect YAMLs and walkthroughs. `scripts/`
has stand-alone helpers, and the `console` launcher bootstraps the interactive
menu.

## Build, Test, and Development Commands
- Create a dev env: `python -m venv .venv && source .venv/bin/activate`
- Install deps: `pip install -e .[dev]`
- Run the console: `./console` (or `enigmatic-dgb console`)
- Run tests: `pytest`
- Run a single file: `pytest tests/test_encoder.py`
- Coverage run: `pytest --cov=enigmatic_dgb`

## Coding Style & Naming Conventions
Use Python 3.9+, standard-library style, and type hints. Formatting is `black`;
run `black .` when editing logic-heavy modules. Indentation is 4 spaces,
functions/modules use `snake_case`, classes use `PascalCase`, and constants use
`UPPER_CASE`. Keep state in CLI/console/watcher layers and favor pure functions
in core modules.

## Testing Guidelines
Tests live in `tests/` and follow `test_*.py` naming. `pytest` must pass for
every PR. Add coverage for new encoder/decoder behavior and CLI flows. If you
touch RPC behavior, include a dry-run example or clear steps to exercise it on
regtest/testnet.

## Commit & Pull Request Guidelines
Commit messages are short, imperative summaries (for example: "Add", "Fix",
"Improve"). PRs should explain why the change matters, not only what changed.
If you modify specs, call it out explicitly. New CLI commands must be documented
in `docs/TOOLING.md` and `docs/simple_usage.md`. New examples or dialects should
be added to `examples/README.md`. Docs/spec PRs should include rendered previews
or screenshots to validate formatting.

## Configuration & Security Tips
RPC settings come from `DGB_RPC_USER`, `DGB_RPC_PASSWORD`, `DGB_RPC_HOST`,
`DGB_RPC_PORT`, and `DGB_RPC_WALLET`, or `~/.enigmatic.yaml`. Keep credentials
out of commits. Security reports should be sent privately to the maintainers.
