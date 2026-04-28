# Architecture

Decisions and rationale for `enocean-async-tui`. Companion to `roadmap.md`.

This document captures decisions taken at design time. When a decision is
revisited, append the new decision below the old one with a date and a short
rationale rather than rewriting history — the trail of "why" is more valuable
than a single tidy answer.

## Stack recap

- Python 3.14, managed by `uv`.
- Textual ≥ 8.2 for the UI. Async-native, asyncio-based event loop.
- `enocean-async` for ESP3 over serial. Shares the asyncio loop with Textual.
- Tooling: ruff (lint + format), mypy strict, pytest + pytest-asyncio,
  pre-commit, pylint.

## Service layer (A1) — single async iterator, evolve later

Decision: a single `DongleService` exposes telegrams as an async iterator. A
single `DeviceManager` consumes that iterator and dispatches per-device
events to the UI via Textual messages.

```
enocean-async ──► DongleService.telegrams() ──► DeviceManager ──► Textual messages ──► widgets
```

Why not an internal pub/sub bus from day 1? YAGNI. With one consumer
(`DeviceManager`) the bus adds plumbing without payoff. We revisit if a
second consumer (e.g. an MQTT bridge in Phase 5) appears.

Backpressure plan: `DongleService` exposes a bounded `asyncio.Queue` (size
≈ 256). On overflow we drop oldest **and** emit a warning telegram-event so
the UI can flash a banner. Telegrams are tiny and the consumer is fast; this
is a safety net, not a hot path.

## Decoder organisation (A2) — registry of classes

Decision: one decoder class per EEP, registered via a decorator into a
module-level dict. Lookup key is the `(rorg, func, type)` triple.

```python
@register_eep("F6-02-01")
class RockerSwitchDecoder(Decoder[RockerReading]):
    rorg = 0xF6
    func = 0x02
    type = 0x01

    def decode(self, telegram: Telegram) -> RockerReading:
        ...
```

Why classes and not a flat dict of callables? Each EEP often needs both
`decode` (telegram → reading) and `encode` (command → telegram, for
actuators). Pairing them in one class keeps the symmetry obvious and gives
a clean unit-test target.

Why not setuptools entry-points for plugins? Premature. We keep the
registry import-driven; if external plugins become a need (Phase 5), the
registry can adopt entry-points without touching call sites.

Decoder discovery: `enocean_async_tui.decoders.__init__` imports each EEP
submodule, which triggers its `@register_eep` side effect. New decoder =
new file + one line in `__init__.py`. No magic auto-discovery.

## Storage abstraction (A3) — `Store` Protocol, JSON now, SQLite later

### Inspiration: how Home Assistant does it

Home Assistant splits storage into two layers, and we mirror that split:

- **Registries (devices, entities, config entries) → JSON files.** HA's
  `homeassistant.helpers.storage.Store` writes versioned JSON to
  `.storage/`, atomically (`tmp + rename`), with an async
  `_async_migrate_func(old_major, old_minor, data) → data` hook that runs
  on load when the on-disk version is older than the code's expected
  version.
- **State history (`recorder` integration) → SQL.** HA's recorder uses
  **SQLite by default** (file `home-assistant_v2.db` in the config
  directory), with optional MariaDB / MySQL / PostgreSQL via SQLAlchemy.
  The default purge keeps ~10 days. SQLite is the right pick at our
  scale; we add it only when we want long-term history (Phase 5).

We do **not** vendor `homeassistant.helpers.storage` — it is tightly
coupled to `homeassistant.core.HomeAssistant` and dragging in HA core for
~150 lines of behaviour is the wrong trade. We mirror the design instead.

### The Protocol

```python
class Store[T](Protocol):
    """Versioned, async, atomic key/value storage."""

    async def load(self) -> T | None:
        """Return data, running `migrate` if the on-disk version is older."""

    async def save(self, data: T) -> None:
        """Atomically write data with the current version."""
```

Concrete implementations:

- **`JsonStore[T]`** (Phases 0–4). Writes to a path via `tmp + os.replace`
  for atomicity. Embeds `{"version": N, "data": {...}}`. On load, if
  `version < current`, runs the supplied `migrate(old_version, data) → data`
  callback in a loop until current.
- **`SqliteStore[T]`** (Phase 5, recorder only). Uses raw `sqlite3` via
  `asyncio.to_thread`. SQLAlchemy is overkill at our scale. Schema
  migrations use a small `schema_versions` table. Runs alongside, not
  instead of, the JSON `Store` for registries.

### Migration policy

- Every `Store` payload carries a `version: int`.
- Bumping the version is mandatory whenever the payload shape changes.
- Migrations are **forward-only**: `migrate(0, data) → data_v1`,
  `migrate(1, data) → data_v2`, …. Each step is unit-tested with a
  golden fixture of the old shape and the expected new shape.
- The Phase 5 JSON → SQLite cutover is not a `Store` migration — it is a
  **storage-backend migration**, exposed as `enocean-tui migrate-storage`.
  It reads via the `JsonStore`, writes via the `SqliteStore`, leaves the
  JSON file in place as a backup for one release cycle.

## Device state model (A4) — typed `Reading` objects

Decision: decoders produce frozen, typed `Reading` dataclasses. A `Device`
holds the latest `Reading` plus a small ring buffer (default 32) for the
detail view.

```python
@dataclass(frozen=True, slots=True)
class RockerReading:
    button: Literal["A0", "A1", "B0", "B1"]
    pressed: bool
    rssi_dbm: int

@dataclass
class Device:
    id: int                       # 32-bit EnOcean ID
    name: str
    eep: tuple[int, int, int]     # rorg, func, type
    last_reading: Reading | None
    history: deque[Reading]       # bounded

    last_seen: datetime
    last_payload: bytes
```

Why not a `Reading` superclass with subclasses? `Reading` is a `Protocol`
or a `Union` of dataclasses, not an inheritance hierarchy. Subclasses cost
us nothing in expressiveness and structural typing is enough.

Why not a flat `state: dict[str, Any]`? Loses type safety and forces the UI
to know which keys each EEP produces. With typed readings the UI can
`match reading: case RockerReading(...): ...` — exhaustive and checked by
mypy.

## TDD discipline (A5) — three test layers per slice

Every device slice ships with all three. None is optional, and none is
written after the implementation it covers.

1. **Decoder unit tests.** Pure, synchronous, no `asyncio`, no mocks.
   Golden input bytes → expected `Reading`. Fixtures live in
   `tests/fixtures/eep-XX-YY-ZZ/*.json` (telegram bytes + expected
   decoded reading). One file per scenario (button A0 pressed, A0
   released, A1 pressed, …).
2. **Manager integration tests.** Drive `DeviceManager` via a
   `FakeDongle` that replays a recorded session. Assert registry shape:
   right device created on teach-in, `last_reading` updates, history
   bounded.
3. **Textual UI tests via `Pilot`.** Boot the app with `FakeDongle`,
   inject teach-in + state telegrams, assert visible content via
   `app.query_one(...)`. Useful for catching wiring bugs (decoder runs
   but reading never reaches the table).

The red-green-refactor cycle, per slice:
1. Write a failing decoder unit test (red).
2. Implement the decoder until it passes (green).
3. Write a failing manager integration test (red).
4. Wire the decoder into `DeviceManager` (green).
5. Write a failing UI test (red).
6. Wire the reading into the table / detail screen (green).
7. Refactor with tests as a safety net.

## Slice "done" criteria (A6) — 60-second demo

A slice is not done until all of these are true:

- All three test layers green.
- Coverage gate not lowered.
- A 60-second demo path exists: start the TUI, exercise the slice, see the
  expected outcome — without restarting, without editing config.
- A short `docs/specs/slices/eep-XX-YY-ZZ.md` exists describing the user
  story, the test fixtures, and the demo path.

## Concurrency notes

- Single asyncio event loop, shared by Textual and `enocean-async`.
- The dongle's serial reader runs as a Textual `Worker` started in
  `App.on_mount`. Cancellation on app shutdown is handled by Textual's
  worker lifecycle.
- The `Store` does its own atomic writes; we do not need a global write
  lock as long as exactly one `Store` instance per file exists per
  process. This is enforced by passing the `Store` through dependency
  injection rather than constructing it ad-hoc.
- UI updates always go through Textual messages, never direct widget
  mutation from the dongle worker. This keeps the data-flow direction
  one-way and trivially thread-safe (asyncio is single-threaded anyway,
  but the discipline matters when we add the optional MQTT bridge).

## Module layout (target)

```
src/enocean_async_tui/
    __init__.py
    app.py                    # Textual App, screens, key bindings
    cli.py                    # argparse / typer entry, --port etc.
    settings.py               # config loading
    dongle/
        __init__.py
        service.py            # DongleService (real)
        fake.py               # FakeDongle (tests, replay)
    devices/
        __init__.py
        manager.py            # DeviceManager
        model.py              # Device, Reading union
        registry.py           # decoder registry, @register_eep
    decoders/
        __init__.py           # imports all EEP modules
        base.py               # Decoder Protocol
        f6_02_01.py           # rocker switch
        d5_00_01.py           # contact
        d2_01_0e.py           # smart plug
        ...
    storage/
        __init__.py
        protocol.py           # Store Protocol
        json_store.py         # JsonStore
        sqlite_store.py       # SqliteStore (Phase 5)
        migrations/           # one module per (file, from_version)
    ui/
        screens/
            sniffer.py
            registry.py
            device_detail.py
        widgets/
            telegram_log.py
            device_table.py
```

## Out of scope (for now)

- Plugin loading from external packages.
- Multi-dongle / repeater coordination.
- Smart-ack mailbox handling.
- Anything that requires a remote service to function.

These can graduate from `roadmap.md` "open questions" if a real use case
arrives.
