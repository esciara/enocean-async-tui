# Phase 0 — Foundation (functional spec index)

Phase-0 ships the platform every later phase depends on: a
`DongleService` that owns the serial connection, a `FakeDongle` test
double, a settings loader, the Textual app shell, and a CI gate. No
EnOcean decoders yet — those start in Phase 3.

This folder is the **single source of truth** for Phase-0 development.
Roadmap and architecture decisions are upstream; everything in this
folder is the level of detail needed to write a failing test without
re-asking design questions.

## Documents

| File | Scope |
|---|---|
| [`enocean-async-notes.md`](./enocean-async-notes.md) | Upstream `enocean-async==0.13.1` API surface — exact class names, method signatures, what `ERP1Telegram` carries (and crucially what it doesn't). |
| [`dongle-service.md`](./dongle-service.md) | `DongleService` — public API, state machine, backoff constants, queue semantics, `RawTelegram` shape, error/`aclose()` semantics. |
| [`fake-dongle.md`](./fake-dongle.md) | `FakeDongle` — `Dongle` protocol conformance, fixture format (JSONL), programmatic test API, replay timing. |
| [`settings.md`](./settings.md) | `Settings` — fields, source precedence, env-var prefix, validation rules, CLI entry point wiring. |
| [`app-shell.md`](./app-shell.md) | Textual app — widget tree, status text mapping, key bindings, fallback modal, lifecycle. |
| [`ci.md`](./ci.md) | GitHub Actions workflow, coverage threshold (`pyproject.toml` `fail_under = 80`), pre-commit parity, dependency-management convention. |

## Status

Track per-component progress here. Update on every PR.

| Component | Doc | Implementation | Tests | DoD |
|---|---|---|---|---|
| Upstream notes | ✅ | n/a | n/a | n/a |
| `DongleService` | ✅ | ✅ | ✅ | ✅ |
| `FakeDongle` | ✅ | ✅ | ✅ | ✅ |
| `Settings` | ✅ | ✅ | ✅ | ✅ |
| App shell | ✅ | ✅ | ✅ | ✅ |
| CI gate | ✅ | ✅ | n/a | ✅ |

✅ = done · 🚧 = in progress · ⏳ = not started · ⛔ = blocked

## Phase-0 development order

The TDD red-green cycle drives the order. Each step is a self-contained
slice of the foundation; later steps depend on earlier ones.

1. **CI gate first.** Land `.github/workflows/ci.yml` and the
   `[tool.coverage.*]` sections in `pyproject.toml`. The gate must be
   green on a no-op PR before any feature lands. Otherwise we end up
   chasing a moving coverage threshold.
2. **`Settings`.** Pure, no asyncio, no Textual — fastest to TDD. Lands
   the `cli.py` entrypoint at the same time and rewires the
   `enocean-tui` script.
3. **`Dongle` protocol + `RawTelegram` types.** No behaviour yet, just
   the shapes both `DongleService` and `FakeDongle` will satisfy.
4. **`FakeDongle`.** Implementing the test double *before* the real
   service means service tests have a foundation to lean on. `FakeDongle`
   tests use only its programmatic API — no production code yet uses it.
5. **`DongleService`.** Built against the `Dongle` protocol; tests use a
   mocked `enocean_async.Gateway` (one per scenario). State machine,
   backoff, queue overflow all driven by failing tests first.
6. **App shell.** Pulls everything together. Pilot UI tests use
   `FakeDongle` via `dongle_factory` injection. Manual smoke run with a
   real (or absent) dongle closes Phase 0.

## Resolved decisions log

These came up during planning and are folded into the per-component docs.
Keeping them here so the rationale is auditable.

| # | Topic | Decision | Where it landed |
|---|---|---|---|
| 1 | `telegrams()` element type | `RawTelegram` wrapping the upstream `ERP1Telegram`. Adds **only** `received_at`; `rssi_dbm` is a passthrough property to upstream. | `dongle-service.md`, `enocean-async-notes.md` |
| 2 | Connection-state surface | Async iterator of `(old, new, at)` transitions via `state_changes()`. Service is Textual-agnostic. | `dongle-service.md` |
| 3 | Backoff parameters | `INITIAL_DELAY_S=0.5`, `MAX_DELAY_S=30`, `MULTIPLIER=2.0`, `JITTER=0.1`. Module constants for monkey-patching. | `dongle-service.md` |
| 4 | Queue overflow signalling | Separate `warnings()` async iterator emitting `QueueOverflowWarning(dropped_count, since)`. | `dongle-service.md` |
| 5 | Storage dir in Phase 0 | Deferred to Phase 2. `Settings` has only `port` + `log_level`. | `settings.md` |
| 6 | Env-var prefix | `ENOCEAN_TUI_*`. | `settings.md` |
| 7 | Coverage gate location | `pyproject.toml [tool.coverage.report] fail_under = 80`. CI passes no `--cov-fail-under`. | `ci.md` |
| 8 | CI matrix | Ubuntu-only, Python 3.14, single matrix entry. | `ci.md` |
| 9 | App start without a dongle | Real `DongleService` raises → modal asks the end-user. Default = Quit. Accept = `FakeDongle(realtime=True)` with header suffix `(fake-dongle mode)`. | `app-shell.md` |
| 10 | Phase-0 header content | Title + status only. Port + base ID land in Phase 1. | `app-shell.md` |
| 11 | Upstream auto-reconnect | Disabled (`auto_reconnect=False`). `DongleService` owns the reconnect loop so backoff matches the spec, not upstream's 5 s linear retry. | `enocean-async-notes.md`, `dongle-service.md` |

## Open questions

None — all design questions are resolved. New questions discovered during
implementation should be added here, answered, then folded back into the
relevant component doc.

## Dependency-management convention

**Always use `uv`.** Never hand-edit `[project.dependencies]` or
`[dependency-groups]` in `pyproject.toml`:

- `uv add <pkg>` — runtime dep
- `uv add --dev <pkg>` — dev dep
- `uv lock --upgrade-package <pkg>` — bump one
- `uv sync --upgrade` — bump all within constraints

Editing `[tool.*]` tables in `pyproject.toml` is fine — those aren't
dependencies. CI runs `uv sync --frozen`, so any drift between
`pyproject.toml` and `uv.lock` fails the build.
