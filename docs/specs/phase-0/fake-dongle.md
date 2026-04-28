# `FakeDongle` — functional spec

In-memory `Dongle` implementation for tests and for the runtime fallback
when the real dongle isn't available (see `app-shell.md` §Modal). Lives at
`src/enocean_async_tui/dongle/fake.py`.

## Conformance

`FakeDongle` is a `Dongle` (the `Protocol` in `dongle/protocol.py` —
see `dongle-service.md`). The same `connect()` / `aclose()` /
`telegrams()` / `state_changes()` / `warnings()` / `send()` surface,
identical types, identical semantics for state transitions and queue
overflow.

Anything written against `Dongle` works against both `DongleService` and
`FakeDongle` without conditionals. This is the type-safety guarantee the
Phase-0 tests rely on.

## Construction

```python
fake = FakeDongle(
    *,
    recording: Path | None = None,
    realtime: bool = False,
    queue_size: int = 256,
)
```

| Parameter | Purpose |
|---|---|
| `recording` | Optional path to a JSONL replay file (see §Fixture format). On `connect()`, replays the file's telegrams into `telegrams()`. `None` = silent until `push()` is called. |
| `realtime` | If `True`, `t_offset_ms` is honoured (`asyncio.sleep`s between events). If `False` (default for tests), events are pushed back-to-back as fast as the consumer drains — keeps unit tests fast. |
| `queue_size` | Same bounded-queue size as `DongleService`. Default mirrors `DongleService.TELEGRAM_QUEUE_SIZE = 256`. |

## Programmatic API (test-only knobs)

These methods extend the `Dongle` protocol; tests cast / use the concrete
type. Production code uses only the protocol surface.

```python
async def push(self, telegram: ERP1Telegram, *, rssi_dbm: int | None = None) -> None:
    """Wrap in RawTelegram(received_at=now()) and enqueue. Honours overflow rules."""

async def push_raw(self, telegram: RawTelegram) -> None:
    """As above but with caller-controlled received_at — for deterministic tests."""

async def simulate_disconnect(self) -> None:
    """Force CONNECTED → RECONNECTING. The fake then reconnects on its own
    backoff (mirrors the real service); tests can inspect state_changes()."""

async def simulate_connection_failure(self, *, attempts: int = 1) -> None:
    """Force connect() to fail `attempts` times before succeeding. Used to
    test reconnect loops."""

def set_state(self, state: State) -> None:
    """Bypass the state machine for pathological-case tests. Emits a
    StateChange. Use sparingly — prefer simulate_*."""
```

`FakeDongle.send()` records calls into a public `sent: list[ESP3Packet]`
list and returns `SendResult(response=None, duration_ms=0.0)` by default;
override via `fake.send_response = SendResult(...)` if a test needs a
specific response.

## Fixture format

Recordings live at `tests/fixtures/recordings/*.jsonl`. One JSON object per
line; no leading/trailing whitespace. Schema:

```jsonc
{
  "t_offset_ms": 0,            // int, ms since recording start. Monotonic.
  "telegram_hex": "f6500029...",// str, hex-encoded raw ERP1 frame (rorg byte + payload + sender + status).
  "rssi_dbm": -65,             // int | null, optional; if null treated as 0xFF (unknown) upstream.
  "comment": "button A0 pressed" // str | null, optional, ignored at runtime.
}
```

Decoding rule: the hex frame is parsed back into an `ERP1Telegram` via
`ERP1Telegram.from_bytes(...)` (or whatever the upstream parser exposes —
`enocean-async-notes.md` shows the entry point under
`enocean_async.protocol.erp1`). On parse failure the line is skipped with
a logged warning; tests should not have parse failures, so the warning
flushes via the test logger and surfaces.

### Naming convention

`tests/fixtures/recordings/{slug}.jsonl` where `{slug}` is `eep-XX-YY-ZZ-{scenario}`
once decoders exist (Phase 3+). For Phase 0 we use generic names:

- `tests/fixtures/recordings/single-rps.jsonl` — one RPS frame, used to
  prove the callback → queue → iterator path.
- `tests/fixtures/recordings/burst-300.jsonl` — 300 frames, used to drive
  the queue-overflow test (300 > 256 default).

### Regeneration

A short helper script (`scripts/record_dongle.py`, written when needed —
not Phase 0) connects to a real dongle and writes JSONL lines using the
schema above. The script is documented in `tests/fixtures/README.md`,
which is created lazily with the first fixture.

## Replay timing

- **Test default (`realtime=False`).** All recorded telegrams are pushed
  into the queue as fast as the consumer drains. `t_offset_ms` is read but
  not slept on — keeps tests deterministic and fast.
- **Realtime (`realtime=True`).** Between events, `await
  asyncio.sleep((t_offset_ms[i] - t_offset_ms[i-1]) / 1000)`. Used for
  the runtime-fallback path so the TUI feels like it has live traffic.
- Replay starts on `connect()` and reschedules on each successful
  reconnect (matching real-dongle behaviour: when the cable comes back,
  telegrams resume).

## State machine

Same five states as `DongleService` (`IDLE → CONNECTING → CONNECTED →
RECONNECTING → CLOSED`). Same backoff constants. Differences:

- `connect()` does no I/O — it just transitions the state and starts the
  replay task. By default it succeeds immediately; use
  `simulate_connection_failure(attempts=N)` to force N failures.
- "Port lost" is triggered by `simulate_disconnect()` only.

## Tests of the fake itself

The fake is library code, so it gets its own unit tests
(`tests/dongle/test_fake.py`):

- Construction with no recording → state IDLE → connect → CONNECTED → no
  telegrams arrive until `push()` called.
- Construction with `single-rps.jsonl` → connect → exactly one
  `RawTelegram` arrives via `telegrams()`; its `rssi_dbm` matches the
  fixture.
- `simulate_disconnect()` → `state_changes()` shows CONNECTED →
  RECONNECTING → CONNECTED.
- `simulate_connection_failure(attempts=2)` → connect retries twice
  before settling on CONNECTED. Total elapsed time consistent with
  monkey-patched `INITIAL_DELAY_S=0.0` (so the test is fast).
- Overflow: `realtime=False` plus `burst-300.jsonl` plus a slow consumer
  → at least one `QueueOverflowWarning` arrives on `warnings()` with
  `dropped_count > 0`.

## Definition of done

- The fake satisfies the `Dongle` protocol (mypy proves this — no
  `# type: ignore`).
- All scenarios above green.
- One recording file per scenario committed to
  `tests/fixtures/recordings/`.
- `tests/fixtures/README.md` exists once the first recording exists,
  documenting schema + regeneration script (or a TODO link to it).
