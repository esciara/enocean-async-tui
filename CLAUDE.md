# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Stack

- **Python 3.14**, managed by [uv](https://docs.astral.sh/uv/)
- **TUI framework**: [Textual](https://textual.textualize.io/) — async-native, integrates directly with asyncio
- **EnOcean backend**: [`enocean-async`](https://pypi.org/project/enocean-async/) — async-first, shares the Textual event loop
- **Build system**: `uv_build` (hatchling-compatible)
- **Source layout**: `src/enocean_async_tui/`

## Commands

Always use `uv run` to invoke Python tools:

- **Run app**: `uv run enocean-tui`
- **Run tests**: `uv run pytest`
- **Lint**: `uv run ruff check src tests`
- **Format**: `uv run ruff format src tests`
- **Type check**: `uv run mypy`
- **Install git hooks**: `uv run pre-commit install`
- **Add dependency**: `uv add <package>`
- **Add dev dependency**: `uv add --dev <package>`

## Architecture Notes

Textual's event loop is asyncio-based. The EnOcean serial/USB listener should run as a Textual `Worker` or as an asyncio task launched from the app's `on_mount` hook, so both loops share the same thread without blocking the UI.
