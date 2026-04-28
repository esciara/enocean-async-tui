# `Settings` — functional spec

Phase-0 configuration loader. Source precedence: **CLI flags > env vars >
defaults**. Pure function: no I/O beyond reading env. Storage directory
and any other Phase 2+ fields are explicitly **not** in scope.

Lives at `src/enocean_async_tui/settings.py`. Loaded once by
`cli.py:main()` and threaded through to `App` / `DongleService` via
constructor injection (no globals, no module-level state).

## Fields

| Field | Type | Default | CLI flag | Env var |
|---|---|---|---|---|
| `port` | `str` | `"/dev/ttyUSB0"` | `--port` | `ENOCEAN_TUI_PORT` |
| `log_level` | `Literal["DEBUG", "INFO", "WARNING", "ERROR"]` | `"INFO"` | `--log-level` | `ENOCEAN_TUI_LOG_LEVEL` |

That's it. Storage dir, log file, base ID etc. land in later phases.

## Dataclass shape

```python
@dataclass(frozen=True, slots=True)
class Settings:
    port: str
    log_level: LogLevel  # the Literal alias above

    @classmethod
    def from_args(cls, argv: Sequence[str] | None = None, *, env: Mapping[str, str] | None = None) -> "Settings":
        """Parse CLI argv (sys.argv[1:] if None) and env (os.environ if None).
        Pure, deterministic, no I/O."""
```

`env` is injectable so unit tests don't have to mutate `os.environ`.

## Source precedence

For each field:

1. If CLI flag present → use it.
2. Else if env var set (non-empty) → use it.
3. Else → use the default.

The CLI parser uses `argparse`; missing-flag detection is via "did argparse
see the flag" rather than "is the value equal to the default", so a user
can explicitly pass `--port /dev/ttyUSB0` and override an env var that
points elsewhere.

Implementation sketch (illustrative — final lives in `settings.py`):

```python
parser = argparse.ArgumentParser(prog="enocean-tui")
parser.add_argument("--port", default=None)
parser.add_argument("--log-level", choices=("DEBUG","INFO","WARNING","ERROR"), default=None)
ns = parser.parse_args(argv)
port = ns.port or env.get("ENOCEAN_TUI_PORT") or "/dev/ttyUSB0"
log_level = ns.log_level or env.get("ENOCEAN_TUI_LOG_LEVEL") or "INFO"
return cls(port=port, log_level=log_level)
```

## Validation

Phase 0 keeps validation minimal:

- `port`: accepted as an opaque string. We do **not** check the path
  exists at parse time — that's `DongleService.connect()`'s job (and its
  failure triggers the FakeDongle modal in `app-shell.md`). Rationale: a
  dongle plugged in *after* startup should be openable.
- `log_level`: the `Literal` plus argparse `choices=` already constrain
  this. Env-var values that aren't one of the four are rejected with a
  clear error from `Settings.from_args` (not a generic `ValueError` —
  raise `SettingsError` defined in the same module).

```python
class SettingsError(ValueError):
    """Raised by Settings.from_args on invalid env-var values."""
```

## Logging configuration

`Settings.from_args` does **not** call `logging.basicConfig`. That's
`cli.py:main()`'s job, called once after settings are loaded:

```python
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    stream=sys.stderr,
)
```

No file handler in Phase 0 (Phase 4 introduces structured JSON-lines
logging per roadmap §Phase 4).

## CLI entry point

```python
# src/enocean_async_tui/cli.py
def main(argv: Sequence[str] | None = None) -> int:
    settings = Settings.from_args(argv)
    logging.basicConfig(level=settings.log_level, ...)
    app = EnoceanTuiApp(settings)
    app.run()
    return 0
```

`pyproject.toml` already declares `enocean-tui = "enocean_async_tui.app:main"`;
**update this to `enocean_async_tui.cli:main`** when the cli module lands.
The change is via `uv` (no manual edits — see `ci.md`).

## Tests

Unit tests at `tests/test_settings.py`. All pure, no asyncio.

| Scenario | Assertion |
|---|---|
| No CLI args, empty env | `port == "/dev/ttyUSB0"`, `log_level == "INFO"`. |
| `--port /dev/ttyACM0` | overrides default. |
| `ENOCEAN_TUI_PORT=/dev/ttyACM1` | overrides default. |
| Both CLI and env set | CLI wins. |
| `--log-level DEBUG` | set on result. |
| Invalid env `ENOCEAN_TUI_LOG_LEVEL=YELL` | `SettingsError` raised. |
| Invalid CLI `--log-level YELL` | argparse `SystemExit` (let it through; argparse already prints a useful message). |

No fixtures, no temp dirs, no monkey-patching `os.environ` (use `env=` kwarg).

## Definition of done

- `Settings.from_args` is pure and tests above pass.
- `cli.py:main` wires settings → logging → app.
- `pyproject.toml [project.scripts]` updated via `uv` (e.g. by editing
  pyproject.toml manually is *not* the convention — see open question
  below).
- mypy strict clean; no `Any` in the public surface.

## Open implementation note

`pyproject.toml [project.scripts]` is not a dependency — it's a project
metadata field. The plan's "use `uv` for deps" rule is about
`[project.dependencies]` and `[dependency-groups]`. Editing
`[project.scripts]` directly in `pyproject.toml` is fine; the implementer
should treat it as data, not as a dependency operation.
