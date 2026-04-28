# CI gate — functional spec

GitHub Actions workflow that gates merges on lint, format, type, and test
passes with coverage ≥ 80 %. Lives at `.github/workflows/ci.yml`.

Cross-references: `pyproject.toml` (already configured), `.pre-commit-config.yaml`
(hooks must stay in sync with this workflow).

## Job definition

Single-job, single-OS, single-Python matrix entry. Pinned for Phase 0;
matrix expansion is a Phase 4+ concern.

| Field | Value |
|---|---|
| Workflow file | `.github/workflows/ci.yml` |
| Trigger | `push` to any branch, `pull_request` against `main` |
| Runs on | `ubuntu-latest` |
| Python | `3.14` (managed by `uv`, not by `setup-python`) |
| Concurrency | Cancel in-progress runs for the same branch on new push |

## Steps

In order:

1. **Checkout** — `actions/checkout@v4`.
2. **Install `uv`** — `astral-sh/setup-uv@v3` (or current major). Pin the
   `uv` version in the workflow file (don't rely on `latest`) so CI
   reproduces locally.
3. **Sync deps** — `uv sync --frozen`. `--frozen` ensures `uv.lock` is
   honoured exactly; CI fails if the lock is out of date.
4. **Lint (ruff check)** — `uv run ruff check src tests`.
5. **Format check (ruff format)** — `uv run ruff format --check src tests`.
   `--check` makes it fail if any file would be reformatted.
6. **Type check** — `uv run mypy`. Reads strict config from
   `pyproject.toml [tool.mypy]`.
7. **Tests with coverage** — `uv run pytest --cov`. **No `--cov-fail-under`
   on the command line** — the threshold lives in `pyproject.toml`.

## Coverage threshold

Single source of truth: `pyproject.toml [tool.coverage.report]`.

```toml
[tool.coverage.report]
fail_under = 80
show_missing = true
skip_covered = false

[tool.coverage.run]
branch = true
source = ["enocean_async_tui"]
```

This config is **added by the implementer in Phase 0** — it's not in the
current `pyproject.toml`. Use `uv` for any dependency tweaks; this is a
config-only change so it's a direct edit. After the change, `uv run
pytest --cov` enforces the gate locally and in CI without further flags.

The 80 % gate is the floor for Phase 0; per `roadmap.md` §Cross-cutting
tracks, the threshold rises 5 % per completed phase. The implementer
should not raise it inside Phase 0 — that's a Phase-1 opening move.

## Pre-commit parity

`.pre-commit-config.yaml` already runs `ruff` (with `--fix`) and `ruff-format`
and `mypy`. Phase 0 keeps it as-is. Two parity rules:

- The CI workflow runs **the same commands** as pre-commit, so a
  developer who runs `uv run pre-commit run --all-files` locally sees
  the same outcome as CI (modulo the test+coverage step, which
  pre-commit doesn't run for speed reasons).
- Versions of `ruff` and `mypy` in `.pre-commit-config.yaml` should
  match the dev-group versions in `pyproject.toml`. When bumping either
  via `uv add --dev <pkg>@<version>`, also bump the corresponding
  `rev:` in `.pre-commit-config.yaml` in the same commit.

## Branch protection (manual, not in YAML)

Configured in the GitHub repo settings, not committed code. Required
checks:

- The `ci` workflow must pass on `main` and on PRs.
- Linear history preferred (no merge commits) — squash-merge for PRs.

## Conventions

- **Always use `uv` for dependency operations.** `uv add <pkg>` /
  `uv add --dev <pkg>` / `uv lock --upgrade-package <pkg>` /
  `uv sync --upgrade`. **Never** hand-edit `[project.dependencies]` or
  `[dependency-groups]` in `pyproject.toml`. CI's `uv sync --frozen`
  catches drift.
- Config-only edits (`[tool.*]` tables) in `pyproject.toml` are fine.

## Workflow YAML sketch

Final file is the implementer's job. This is a structural reference:

```yaml
name: ci
on:
  push:
  pull_request:
    branches: [main]
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          version: "0.10.10"        # match pyproject build-system pin if practical
      - run: uv sync --frozen
      - run: uv run ruff check src tests
      - run: uv run ruff format --check src tests
      - run: uv run mypy
      - run: uv run pytest --cov
```

## Tests

CI itself isn't directly testable from inside the repo. The "did we get
this right?" loop is:

- Open the first Phase-0 PR.
- Confirm the `ci` workflow runs all six steps.
- Deliberately commit a coverage drop and confirm the workflow fails
  with a coverage error pointing at `tool.coverage.report.fail_under`.
- Revert.

## Definition of done

- `.github/workflows/ci.yml` exists, all steps as above.
- `pyproject.toml` has `[tool.coverage.run]` and `[tool.coverage.report]`
  sections with `fail_under = 80` and branch coverage on.
- `uv sync --frozen` works in a clean clone (lock is committed).
- A green CI run on the Phase-0 PR.
- `.pre-commit-config.yaml` and CI both pass on the same code.
