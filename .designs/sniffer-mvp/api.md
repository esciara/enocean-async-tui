# API & Interface Design

## Summary

Phase 1 (Sniffer MVP) adds a modest but meaningful surface to the CLI and
programmatic API inherited from Phase 0. The primary CLI addition is a `--fake`
flag for hardware-free demos; the primary programmatic additions are the
`TelegramReceived` Textual message, the `SnifferWorker` class, the `TelegramLog`
widget, and the `format_telegram()` pure function. All new surfaces follow the
patterns already established in Phase 0 (argparse CLI, `reactive` attributes,
`run_worker()` workers, `ModalScreen` modals).

The most consequential interface decision is how the filter input is exposed: an
inline bar (tcpdump-style) is the clear winner over a modal dialog for a keyboard-
driven sniffer tool. The second-most consequential is the `Settings` extension:
adding `fake: bool` to `Settings` cleanly decouples the CLI from the app,
preserves testability, and avoids the anti-pattern of checking `--fake` inside
`app.py`. All other Phase 1 API additions are low-risk extensions of existing
patterns.

## Analysis

### Key Considerations

- **Phase 0 contract is fixed.** `DongleService`, `FakeDongle`, `Settings`,
  and `EnoceanTuiApp` public APIs are not changed — Phase 1 adds only.
- **The tool's identity is `tcpdump` for EnOcean.** Every interface decision
  should favour the developer/maker mental model: terse, keyboard-driven,
  Unix-tool ergonomics. Modals and confirmation dialogs are friction.
- **Textual conventions must be followed.** Bindings as `BINDINGS` class var,
  actions as `action_*()` methods, message handlers as `on_*()` methods, reactives
  via `reactive[T]`. Deviation creates surprises for contributors.
- **`mypy --strict` is a hard gate.** Every new type must be fully annotated;
  `int | None` patterns must be handled explicitly.
- **Auto-discovery hides complexity.** The user should never need to know serial
  port paths for common hardware — the app should find the dongle automatically.
- **Demo-ability in 60 s.** `uv run enocean-tui` with no flags must reach a
  functional sniffer state (real or fake) without any user-supplied knowledge.

### Options Explored

#### Option 1: No `--fake` CLI flag — modal-only fallback

- **Description**: Phase 0 already has a `FallbackModal` that offers fake-dongle
  mode when the port is unavailable. No new flag is added; a user wanting fake
  mode simply provides no `--port` and accepts the modal.
- **Pros**: Zero new CLI surface; demo path exists via modal.
- **Cons**: Not scriptable. `uv run enocean-tui` on a dongle-less machine prompts
  a modal that blocks automated demos (talks, CI screenshots). Scenario C is
  inherently interactive.
- **Effort**: None

#### Option 2: Add `--fake` flag (Recommended)

- **Description**: `--fake` bypasses dongle connection entirely; starts immediately
  in `FakeDongle` mode with the bundled `burst-300.jsonl` recording. The modal is
  never shown. If both `--port` and `--fake` are given, `--fake` wins with a
  warning.
- **Pros**: Makes Scenario C fully scriptable. Consistent with how test-double flags
  work in similar tools (`--dry-run`, `--mock`). Removes interactive friction for
  speakers and CI pipelines.
- **Cons**: Adds one flag to `--help`. Possible confusion if users think `--fake`
  means "test mode" and don't realise real telegrams won't appear.
- **Effort**: Low — one `bool` field in `Settings`, one `if settings.fake:` branch
  in `_launch_dongle`.

#### Option 3: Add `--fake` + `--replay PATH` flags

- **Description**: `--fake` forces fake mode; `--replay PATH` supplies a custom
  recording file to replay instead of the bundled fixture.
- **Pros**: Enables user-supplied recordings (e.g., from a previous session).
- **Cons**: `--replay` is Phase 4 scope (file logging). Adding it now couples the
  CLI to a feature that doesn't exist yet. The fixture path is an implementation
  detail.
- **Effort**: Low to add, but scope-creep.

---

#### Option A: Expose `max_lines` as a CLI flag

- **Description**: `--max-lines N` sets the `RichLog` retention bound.
- **Pros**: Discoverable via `--help`; useful for long-running sessions.
- **Cons**: This is a power-user tuning knob, not a first-class feature. Adding
  it to `--help` adds visual noise for the 99% case. The default (10 000) is
  correct for all realistic scenarios.
- **Effort**: Low

#### Option B: Expose `max_lines` as env var only (Recommended)

- **Description**: `ENOCEAN_TUI_MAX_LINES=N` configures retention. Not surfaced in
  `--help`. `Settings` carries `max_lines: int` with a default.
- **Pros**: Keeps `--help` clean. Consistent with the existing env-var pattern
  (`ENOCEAN_TUI_PORT`, `ENOCEAN_TUI_LOG_LEVEL`). Power users who need to tune it
  will find it in the README.
- **Cons**: Not discoverable from `--help` alone.
- **Effort**: Low

---

#### Option I: `TelegramReceived` carries `RawTelegram`

- **Description**: Worker posts `TelegramReceived(telegram: RawTelegram)`; the
  screen's `on_telegram_received()` handler calls `format_telegram()`.
- **Pros**: Worker stays pure (no display concerns). Formatting is co-located with
  display logic in the screen. `RawTelegram` is the natural domain object produced
  by the dongle layer.
- **Cons**: `format_telegram()` is called synchronously in the event-loop message
  handler, but it is a pure CPU-bound function — no I/O, no awaits, ≤ 1 µs per
  telegram. No concern in practice.
- **Effort**: Low

#### Option II: `TelegramReceived` carries `FormattedTelegram`

- **Description**: Worker calls `format_telegram()` before posting.
- **Pros**: Message payload is immediately display-ready.
- **Cons**: Worker now imports display types (`FormattedTelegram`, `format_telegram`)
  — breaks the separation between dongle pipeline and UI layer. Harder to test the
  worker in isolation.
- **Effort**: Low

---

#### Option X: Filter bar as modal dialog

- **Description**: `f` pushes a `ModalScreen` with a text input. User types the
  sender ID and presses OK/Cancel.
- **Pros**: Full-screen focus; hard to accidentally dismiss.
- **Cons**: Modal is heavyweight for a sniffer feature. Interrupts the live log
  view (modal occludes content). Inconsistent with the tcpdump analogy. The existing
  `FallbackModal` is used for a blocking decision (quit vs. fake) — filter is not
  that kind of decision.
- **Effort**: Low–Medium

#### Option Y: Filter bar as inline `Input` at bottom of log (Recommended)

- **Description**: `f` reveals an `Input` widget docked at the bottom of
  `SnifferScreen`, styled as a compact bar. The `RichLog` fills the rest. Typing
  applies a CSS "pending" class (italic/dim) to the input; Enter applies the filter;
  Escape clears filter and hides the bar.
- **Pros**: Log stays visible while typing. Standard TUI search-bar idiom (vim, less,
  lazygit). Non-disruptive. Easy to dismiss with Escape.
- **Cons**: Requires hiding/showing the `Input` widget; a small amount of CSS and
  widget lifecycle management.
- **Effort**: Low

---

#### Option P: Pause at widget level — `TelegramLog` owns `_paused` state

- **Description**: `SnifferScreen` calls `telegram_log.toggle_pause()`; the widget
  manages `_paused`, `_pause_buffer`, and `_dropped_count`.
- **Pros**: Self-contained widget. Easier to unit-test in isolation (feed telegrams,
  toggle pause, assert buffer state).
- **Cons**: The `PAUSED` banner must live inside the widget or be signalled to the
  screen for rendering — slight coupling.
- **Effort**: Low

#### Option Q: Pause at screen level — `SnifferScreen` owns `_paused` state (Recommended)

- **Description**: `SnifferScreen` owns `_paused: reactive[bool]`. The `PAUSED`
  banner is a `Label` in the screen (not the widget), reactive on `_paused`. The
  `TelegramLog` widget exposes `action_toggle_pause()` which calls back to the screen's
  reactive, or the screen directly manages the buffer.
- **Pros**: Screen owns all state; cleaner separation between "where state lives" and
  "what renders it". Consistent with Phase 0's pattern: `StatusHeader` receives state
  from the app via `reactive`, doesn't manage state itself.
- **Cons**: Screen and widget are more coupled via the reactive system.
- **Effort**: Low

**Further analysis:** The design-doc (§3.3–§3.4) already specifies filter state and
pause state on `SnifferScreen`. Follow that. `TelegramLog` is a presentational widget;
`SnifferScreen` is the controller.

### Recommendation

**CLI**: Add `--fake` flag (Option 2). Expose `max_lines` as env-var only (Option B).

**Programmatic API**:
- `TelegramReceived(Message)` carries `RawTelegram` (Option I).
- `SnifferScreen` owns `filter_id: int | None` and `_paused: bool` state (Option Q).
- Filter bar is an inline `Input` at the bottom of `SnifferScreen` (Option Y).
- Formatting is a pure function `format_telegram(t: RawTelegram) -> FormattedTelegram`
  in `ui/formatters.py`.

**Full proposed interface surface for Phase 1:**

```python
# ui/messages.py
class TelegramReceived(Message):
    def __init__(self, telegram: RawTelegram) -> None:
        super().__init__()
        self.telegram = telegram


# ui/formatters.py
def format_telegram(t: RawTelegram) -> FormattedTelegram: ...


# ui/workers/sniffer.py
class SnifferWorker:
    """Textual @work coroutine; iterates DongleService.telegrams()."""
    async def run(self) -> None: ...     # started via run_worker()
    def pause(self) -> None: ...         # called by SnifferScreen.action_toggle_pause
    def resume(self) -> None: ...        # called by SnifferScreen.action_toggle_pause
    def clear_buffer(self) -> None: ...  # called on 'c' while paused


# ui/screens/sniffer.py
class SnifferScreen(Screen[None]):
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("c", "clear", "Clear"),
        ("p", "toggle_pause", "Pause/Resume"),
        ("f", "enter_filter", "Filter"),
    ]

    filter_id: reactive[int | None]   # None = no filter
    _paused: bool                      # not reactive; toggled in action_toggle_pause
    _buffer: list[FormattedTelegram]   # max 10 000
    _pause_buffer: deque[FormattedTelegram]  # maxlen=256
    _dropped_count: int

    def on_telegram_received(self, event: TelegramReceived) -> None: ...
    def action_clear(self) -> None: ...
    def action_toggle_pause(self) -> None: ...
    def action_enter_filter(self) -> None: ...


# ui/widgets/telegram_log.py
class TelegramLog(Widget):
    """Thin wrapper around RichLog. Presentational only."""
    def append(self, ft: FormattedTelegram) -> None: ...
    def clear(self) -> None: ...
    def re_render(self, entries: list[FormattedTelegram]) -> None: ...


# settings.py (extended)
@dataclass(frozen=True, slots=True)
class Settings:
    port: str
    log_level: LogLevel
    fake: bool          # NEW — True when --fake flag given
    max_lines: int      # NEW — from ENOCEAN_TUI_MAX_LINES, default 10_000
```

**Proposed `--help` output:**

```
usage: enocean-tui [-h] [--port PORT] [--fake] [--log-level LEVEL]

Live EnOcean telegram sniffer. Keys: q quit  c clear  p pause  f filter

options:
  -h, --help            show this help message and exit
  --port PORT           Serial port (e.g. /dev/ttyUSB0). Auto-detected if omitted.
  --fake                Start in fake-dongle mode (demo without hardware).
  --log-level LEVEL     Log verbosity: DEBUG / INFO / WARNING / ERROR. Default: INFO.
```

**Filter input UX flow:**

```
1. User presses 'f'
   → FilterBar (Input widget, docked bottom) becomes visible and focused
   → Input label shows "Filter sender ID (8 hex digits):"
   → Log pane becomes dimmed (CSS class "filtering")

2. User types (e.g. "ABCD1234" or "0xABCD1234")
   → Input shows real-time validation: red border for non-hex / >8 chars
   → Log does NOT update while typing ("pending" state)

3. User presses Enter
   → "0x" prefix stripped, case-normalized, parsed to int
   → FilterBar hides; log re-renders showing only matching entries
   → Footer shows: "Filter: 0xABCD1234  [f clear]"

4. User presses 'f' again (or Escape while bar visible)
   → filter_id = None; full log re-renders; FilterBar hides
```

**Log line format (confirmed from PRD):**

```
2026-05-07T14:23:01.042  0xABCD1234  RPS (0xF6)  F600  RSSI -62 dBm
```

Column order: timestamp · sender_id · rorg_name · payload_hex · rssi. Two-space
separator between columns for scan-readability. RSSI `None` → `RSSI – dBm`.

## Constraints Identified

- **`--fake` and `--port` are mutually exclusive.** If both are given, `--fake`
  wins silently (not an error — scripted demos should not break if a port is also
  configured). A `_LOGGER.warning` is emitted so it shows up in debug output.
- **Filter input: `0x` prefix must be accepted.** The PRD clarification (Q5) is
  explicit: "Filter input: accepts `0x` prefix (strips it for matching)." The
  validator must allow `0x` + up to 8 hex chars as a valid input form.
- **Filter input: max 8 hex digits.** EnOcean sender IDs are 32-bit (8 hex digits).
  Inputs longer than 8 hex digits (after stripping `0x`) must be rejected in the
  validator.
- **`mypy --strict` must pass.** `reactive[int | None]` is the correct annotation;
  `int | None` as a bare attribute default (not reactive) is also fine for private
  state. No `Any` escape hatches.
- **`Settings` is `frozen=True`.** Adding `fake: bool` and `max_lines: int` is
  additive and does not change the frozen/slots contract.
- **No new runtime dependencies.** `argparse` is stdlib; no third-party CLI library
  (click, typer) needed or permitted for Phase 1.
- **`format_telegram()` must be synchronous and non-blocking.** It is called on the
  Textual event loop (inside the message handler). `datetime.now()`, string
  formatting, and integer arithmetic qualify. No I/O.
- **`ENOCEAN_TUI_MAX_LINES` env var must accept only positive integers.** A
  `SettingsError` (existing exception class) is raised for invalid values, consistent
  with how `ENOCEAN_TUI_LOG_LEVEL` validation works today.

## Open Questions

1. **`action_quit` vs `app.exit()`**: Phase 0 has `("q", "quit", "Quit")` on
   `EnoceanTuiApp`. Phase 1's `SnifferScreen` also wants `q` to quit. Should the
   binding live on the App (existing) or be re-declared on the screen (override)?
   Textual binding resolution traverses the screen stack then the app; keeping it on
   the App is cleaner and avoids double-binding.

2. **Footer display of active filter**: When a filter is active, the footer should
   show `Filter: 0xABCD1234` alongside the key hints. Does Textual's standard
   `Footer` widget support dynamic runtime text, or does Phase 1 need a custom
   `StatusBar` widget for this? If a custom widget is needed, that is a mild scope
   increase. Alternative: show a `Label` banner above the `FilterBar` docked area
   (zero new widget required).

3. **`SnifferWorker` lifecycle on reconnect**: When the dongle disconnects and
   reconnects, `SnifferScreen` needs to either restart the `SnifferWorker` or signal
   it to re-enter the telegram loop. The design-doc shows an outer retry loop inside
   the worker (`await self._wait_for_reconnect()`). This requires the worker to hold
   a reference to `DongleService`'s state-change event. Is the state-change `AsyncIterator`
   safe to re-iterate after reconnect, or must a fresh iterator be obtained? This
   is a dongle API question, not an interface design question — flagged for the
   integration / implementation dimension.

4. **`PAUSED — N queued` banner placement**: The design-doc specifies an inline
   banner on the log pane. Should this be a `Label` overlaid (Textual `Layer`) or
   a `Static` docked at the top of the log? Docked is simpler (no layer/z-index
   handling). Overlay is more visually impactful. Recommendation: docked `Static`
   with `display: none` until paused, shown above `TelegramLog`.

5. **`ENOCEAN_TUI_MAX_LINES` default**: 10 000 matches `RichLog(max_lines=10_000)`.
   Should the two values be derived from the same constant, or set independently?
   Recommendation: `DEFAULT_MAX_LINES = 10_000` in `settings.py`; passed into
   `SnifferScreen` and used for both `RichLog` and `_buffer` cap.

## Integration Points

- **Data Model** (`data.md`): `FormattedTelegram` shape is defined there.
  The `format_telegram()` function in `ui/formatters.py` must produce exactly
  the `FormattedTelegram` the data model specifies (including `sender_int: int`
  and `line: str`). The `line` field's format must match the log line spec from
  the PRD. These two dimensions must agree on the exact field values and types
  before `formatters.py` is written.

- **Integration Analysis** (`integration.md`): Confirmed Phase 1 is persistence-free.
  The `Store` Protocol is not touched. `SnifferWorker` integration into `app.py`
  follows the pattern in §3 of that document. The `base_id` property (`Dongle`
  Protocol extension) is flagged there — Phase 1 shows `–` in the header, so the
  header widget needs to handle `base_id: int | None` where `None` renders as `–`.
  This is a minor extension to `StatusHeader.render()`.

- **Implementation** (rust polecat): Owns `SnifferWorker` and `SnifferScreen`.
  The `pause()`/`resume()`/`clear_buffer()` API on `SnifferWorker` and the
  `set_filter()` semantics must match what is specified here. The `_telegrams_worker`
  stub in `app.py` is the seam point.

- **UX Analysis** (if a separate dimension): Filter interaction UX (Option Y above)
  and pause banner (OQ4) are UX decisions documented here — they should be confirmed
  or overridden by a UX analysis if one exists. No conflict expected; the decisions
  follow established TUI conventions.

- **Phase 2** (future): `Settings.fake: bool` and `Settings.max_lines: int` become
  part of the public config contract. Both are additive; Phase 2 can add further
  fields without breaking Phase 1. The `--fake` flag should stay in Phase 2+ as
  a supported demo mechanism.
