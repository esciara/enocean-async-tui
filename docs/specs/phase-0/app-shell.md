# App shell — functional spec

Phase-0 Textual app shell. Header shows status; main pane is a placeholder;
footer shows key bindings. Owns the `DongleService` lifecycle and the
fallback-to-`FakeDongle` modal.

Lives at `src/enocean_async_tui/app.py` (evolves from the existing
14-line stub). Cross-references: `dongle-service.md`, `fake-dongle.md`,
`settings.md`.

## Widget tree

```
EnoceanTuiApp                              (Textual App)
├── Header (custom)                        — title + dongle status text
├── Static "Phase 0 — placeholder"         — main pane (replaced in Phase 1+)
└── Footer                                 — key bindings (auto-rendered by Textual)
```

The `Header` widget is custom (not Textual's built-in `Header`) because we
need to render dynamic status text alongside the title. Implemented as a
small `Static` subclass with a reactive `status: State` attribute.

### Title

Static: `"EnOcean TUI"`. Phase 1 will append port + base ID.

### Status text mapping

Verbatim text shown for each `DongleService` state:

| State | Header text | Colour (Textual `style=`) |
|---|---|---|
| `IDLE` | `connecting…` | dim |
| `CONNECTING` | `connecting…` | yellow |
| `CONNECTED` | `connected` | green |
| `RECONNECTING` | `reconnecting…` | yellow |
| `CLOSED` | `closed` | red |
| (FakeDongle fallback active) | `connected (fake-dongle mode)` | magenta |

The "fake-dongle mode" suffix is appended when `App` is wired up with a
`FakeDongle` instance (whether it was a fallback or a `--fake` flag in
some future phase). The `App` knows because it constructs the dongle.

## Key bindings

Phase 0 only:

| Key | Action |
|---|---|
| `q` | Quit (`action_quit`). |
| `Ctrl+C` | Quit (Textual's default). |

Phase 1 adds `c` (clear), `p` (pause), `f` (filter) — not in this spec.

## Lifecycle

```
App.__init__(settings: Settings, *, dongle_factory: Callable[[], Dongle] | None = None)
        │
        ▼
App.compose() → Header, Static, Footer
        │
        ▼
App.on_mount()
   ├─ instantiate dongle = dongle_factory() if provided
   │  else dongle = DongleService(settings.port)
   ├─ try: await dongle.connect()
   │  except ConnectionError:
   │     → push FallbackModal — see §Modal
   ├─ start three Textual Workers, one per stream:
   │     state_worker:   async for change in dongle.state_changes(): header.status = change.new
   │     telegrams_worker: async for tg in dongle.telegrams(): pass   # placeholder; Phase 1 logs
   │     warnings_worker:  async for w in dongle.warnings(): self.notify(...)
   ▼
App.on_unmount()
   └─ await dongle.aclose()
```

`dongle_factory` is constructor-injected so tests can pass a `FakeDongle`
directly without monkey-patching. Production code never passes one;
production fallback to `FakeDongle` happens through the modal, not the
factory.

## Modal: "fall back to fake-dongle mode?"

When `dongle.connect()` raises (port doesn't exist or can't be opened) and
the dongle is a real `DongleService`:

1. App pushes a Textual `ModalScreen` titled "Dongle not available".
2. Body text: `Couldn't open serial port {settings.port}. Continue in
   fake-dongle mode for testing?`
3. Buttons:
   - `[ Quit ]` (default — receives focus on open). Action:
     `app.exit(return_code=2)`.
   - `[ Continue with fake dongle ]`. Action: dismiss modal, instantiate
     `FakeDongle(realtime=True)`, call its `connect()`, set the
     fake-mode suffix on the header.
4. On `Esc`: same as Quit.

Implementation: a `FallbackModal(ModalScreen[bool])` — yields `True` if
the user accepts fallback, `False` (or never resolves, due to exit)
otherwise.

## Concurrency notes (architecture §Concurrency)

- Textual's event loop is the only loop. `DongleService` shares it.
- Each subscriber stream runs as a Textual `Worker` started in
  `on_mount`. Workers are auto-cancelled by Textual on app shutdown,
  satisfying the architecture's "cancellation handled by Textual's worker
  lifecycle" rule.
- Header updates always come through Textual messages (worker → reactive
  attribute → re-render), never direct widget mutation from the dongle
  callback.

## Tests (Pilot UI layer)

`tests/test_app.py`. Each scenario uses `App.run_test()` and a
`FakeDongle` injected via `dongle_factory`.

| Scenario | Assertion |
|---|---|
| App starts, fake immediately connects | Header renders `"connected"` (or `"connected (fake-dongle mode)"` — see open question). |
| Fake transitions CONNECTED → RECONNECTING via `simulate_disconnect()` | Header renders `"reconnecting…"` within one event-loop turn. |
| Press `q` | App exits cleanly, `dongle.aclose()` was awaited (assert via fake's `closed: bool`). |
| Real `DongleService` constructor used, `connect()` raises `ConnectionError` | Modal appears with title "Dongle not available". |
| In modal, press `Quit` | App exits with code 2 and no fake dongle was constructed. |
| In modal, press `Continue with fake dongle` | Modal dismissed, header shows `"connected (fake-dongle mode)"`. |
| Queue overflow warning | A Textual notification (`self.notify(...)`) is visible (assert via `app.notifier.notifications`). |

The "real DongleService raises ConnectionError" tests use a tiny stub that
implements the `Dongle` protocol and raises on `connect()`. Avoids
needing a real serial port in CI.

## Definition of done

Mirrors roadmap §Phase 0 DoD plus the modal-specific bits:

- `uv run enocean-tui --port /dev/ttyUSB0` opens the TUI; if the port
  exists, header reads `connected`. If it doesn't, the modal appears.
- Pressing `q` exits cleanly and `aclose()` is awaited.
- Unplugging the dongle moves the header to `reconnecting…` within one
  backoff cycle (≤ ~1 s with default `INITIAL_DELAY_S = 0.5`).
- All Pilot scenarios green.
- `mypy --strict` clean.
