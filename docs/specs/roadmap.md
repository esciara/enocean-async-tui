# Roadmap

A phased, MVP-style plan for `enocean-async-tui`: a Textual-based TUI for pairing
with EnOcean devices, displaying their state, and sending commands.

Each phase ships an end-to-end usable product. Phases 2 and 3 from the original
sketch are collapsed into a stream of **device slices** — one EEP at a time,
each slice end-to-end (decode → display → control), so we always have something
demo-able.

## Guiding principles

- **TDD red-green-refactor is non-negotiable.** No production code is added
  without a failing test that justifies it. CI gates on tests, ruff, and mypy
  strict from Phase 0 onward.
- **Vertical slices over horizontal layers.** A slice that only supports one
  device type but works end-to-end beats a half-built generic framework.
- **Demo-able in 60 seconds.** A slice is "done" when a user can start the
  TUI, exercise the slice, and see the expected outcome without touching
  config files or restarting the app.
- **Storage starts simple, migrates cleanly.** Versioned JSON via a `Store`
  helper modelled on Home Assistant's `homeassistant.helpers.storage.Store`.
  SQLite is reserved for long-term history (Phase 5), guarded by a Protocol so
  migration is one CLI command, not a rewrite.
- **Thin abstractions only.** YAGNI. We add layers when a second concrete
  use case demands them, not in anticipation.

## Phase 0 — Foundation

The platform every later phase depends on. No EnOcean decoding yet.

Scope:
- `DongleService`: thin async wrapper around `enocean-async`. Exposes
  `connect()`, `telegrams()` async iterator, `send(telegram)`, and a
  connection-state observable.
- `FakeDongle`: in-memory implementation for tests, emits canned telegrams
  from a fixture file or programmatically.
- Settings loader: serial port, log level, storage directory. Sources:
  CLI flags (`--port`, `--log-level`), env vars, defaults.
- App shell: header (dongle status), main pane (placeholder), footer
  (key bindings). Quit on Ctrl+C / `q`.
- CI gate (GitHub Actions or equivalent): ruff, mypy strict, pytest with
  coverage threshold (start at 80%).

Definition of done:
- `uv run enocean-tui --port /dev/ttyUSB0` opens the TUI, shows
  "connected" or "disconnected" in the header, exits cleanly.
- Unplugging the dongle moves status to "reconnecting" with backoff.
- Test suite green, coverage ≥ 80%.

## Phase 1 — Sniffer MVP (read-only telegram log)

The smallest already-useful product: a live tcpdump-style view of EnOcean
traffic. No decoding beyond raw RORG/payload split.

Scope:
- Header: dongle status, port, base ID.
- Main pane: scrolling `RichLog` of telegrams — timestamp, sender ID, RORG
  (RPS / 1BS / 4BS / VLD), raw payload hex, RSSI/dBm.
- Footer bindings: `q` quit, `c` clear, `p` pause, `f` filter by sender ID.
- Auto-reconnect with exponential backoff.

Definition of done:
- Pressing a real EnOcean switch (or replaying a recorded session through
  `FakeDongle`) shows the telegram live within ~50 ms.
- Pause/resume works without dropping telegrams (queue while paused).
- Reconnect after dongle unplug resumes the stream automatically.

## Phase 2 — Generic device registry (no decoders yet)

The platform that all device slices plug into. Devices are tracked but their
payloads are still opaque.

Scope:
- Two-pane layout: left = `DataTable` of known devices (ID, name, EEP if
  known else "unknown", last-seen, raw payload), right = telegram log.
- Teach-in mode (`t` key): the next teach-in telegram is captured; user
  enters a name and confirms the EEP (auto-detected when the teach-in
  telegram carries it; manual otherwise — free-text "EEP" field, no
  validation yet).
- Persist registry to `devices.json` via the versioned `Store` helper
  (see `architecture.md` §Storage). Atomic writes, async, version field
  embedded in the payload, migrate hook ready for v2.
- Devices update their `last_seen` and `last_payload` on every matching
  telegram, even when no decoder is registered.

Definition of done:
- Teach in two devices. Both appear in the table. Restarting the app
  remembers them. `last_seen` updates live as telegrams arrive.
- The `Store` helper has a migration test that exercises a synthetic
  `version: 0 → 1` migration.

## Phase 3..N — Device slices (one EEP at a time)

Each slice is its own MVP. The order is your call; the agreed initial order is:

1. **Slice 3.1 — F6-02-01 / F6-02-02 rocker switch** (sensor only)
2. **Slice 3.2 — D5-00-01 single-channel contact** (sensor only)
3. **Slice 3.3 — D2-01-0E smart plug** (actuator: basic then advanced)

Then continue à la carte from the candidate list below.

Each slice has up to three sub-stages, each shipped independently with its
own tests, commit, and demo:

- **a. Decode + display** (always). TDD a decoder for the EEP, plug it
  into the registry, render its `Reading` in the device row and detail
  screen.
- **b. Basic control** (actuators only). Minimum viable command — for a
  smart plug, on/off; for a dimmer, level 0 / 100; for a shutter, up /
  down / stop.
- **c. Advanced control** (actuators only). Ramp times, channel-specific
  parameters, scenes, scheduling — whatever is useful for that EEP.

A slice is done when:
- All three test layers (decoder unit, manager integration, Textual
  `Pilot` UI) pass for the slice's contribution.
- A 60-second demo is possible against a real device or recorded session.

### Candidate device list (pick order as we go)

Sensors (decode + display only):

- `F6-02-01` / `F6-02-02` — rocker switch (PTM 200 / 210). Trivial RPS
  payload, good first target.
- `D5-00-01` — single-channel contact (door/window magnet, 1BS). Validates
  the decoder registry generalises.
- `A5-02-xx` — temperature sensors (range variants).
- `A5-04-01` / `A5-04-02` — temperature + humidity.
- `A5-07-01/02/03` — occupancy / PIR.
- `A5-08-01` — light + occupancy + temperature combo.
- `A5-14-09` — mechanical handle (window: open / tilted / closed).
- `A5-09-04` / `A5-09-05` — CO₂ / VOC.

Actuators (decode + basic + advanced):

- `D2-01-0E` / `D2-01-12` — smart plug (on/off, then metering).
- `A5-38-08` — central command dimmer (on/off → level → ramp/scene).
- `D2-05-00` — shutter / blinds (up/down/stop → position → tilt).
- `A5-20-01` — HVAC valve (setpoint → schedule).
- `D2-50-xx` — ventilation.

## Phase 4 — Polish, scenes, robustness

After enough slices exist that the TUI is useful for a real home setup.

Scope:
- Rename / re-EEP / delete devices from the UI.
- Scenes: named groups of commands fired with one keystroke (e.g.
  "movie night" → dim living room dimmer to 20 %, turn off hallway plug).
- Config import / export (`devices.json` + `scenes.json`, shareable).
- Structured file logging (JSON lines), separate from the on-screen log.
- Error surfaces: invalid EEP at teach-in, send timeout, base-ID mismatch.

Definition of done:
- A non-trivial setup (≥ 5 devices, ≥ 3 scenes) is fully operable from
  the TUI without manual file edits.

## Phase 5 — HA-style recorder (storage upgrade)

Long-term state history with charts.

Scope:
- `SqliteStore` and `SqliteRecorder` implementing the `Store` /
  `Recorder` Protocols. SQLAlchemy is intentionally **not** required —
  raw `sqlite3` over async via `asyncio.to_thread` is enough at our scale.
- One-time CLI: `enocean-tui migrate-storage` reads the JSON `Store`,
  writes SQLite, leaves the JSON in place as a backup.
- Per-device history view: Textual `Sparkline` for numeric readings,
  pageable table for discrete events.
- Optional: MQTT bridge (publish telegrams, subscribe to commands), as a
  separate executable so the core TUI keeps no MQTT dependency.

Definition of done:
- Migration command is idempotent and round-trips: JSON → SQLite → JSON
  produces equivalent data.
- A device with hours of history renders a sparkline within ~200 ms.

## Cross-cutting tracks

These run alongside every phase, not as a separate phase.

- **TDD layout for every slice** — three test layers, written before
  implementation:
  1. Decoder unit tests: golden bytes → expected `Reading`. Pure, sync,
     no mocks.
  2. Manager integration tests: feed telegrams via `FakeDongle`, assert
     registry state.
  3. Textual UI tests via `Pilot`: drive the app, assert table content
     and detail screens.
- **Coverage** — start at 80 %, raise by 5 % each completed phase.
- **Docs** — every slice gets a short `docs/specs/slices/eep-XX-YY-ZZ.md`
  with user stories, telegram fixtures, and acceptance criteria.
- **Recordings** — keep `tests/fixtures/recordings/*.jsonl` of real
  telegram sessions per device, used by both `FakeDongle` and decoder
  tests as golden data.

## Open questions

These will be answered as we go and folded back into the spec:

- How many simultaneous teach-in telegrams should we buffer? (Affects UX
  if two devices teach in close together.)
- Should the dongle base-ID be exposed to the user for outgoing
  telegrams, or hidden behind device-level commands?
- Where does the boundary between "decoder" and "device class" fall when
  a single physical device implements multiple EEPs (e.g., smart plug
  with metering)? Tentative answer: one decoder per RORG/FUNC/TYPE
  triple, one device may aggregate multiple decoders' readings.
