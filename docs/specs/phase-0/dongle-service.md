# `DongleService` — functional spec

Phase-0 wrapper around `enocean_async.Gateway`. Single producer of telegrams
and connection-state changes for the rest of the app.

Cross-references: `architecture.md` §A1 (service layer), §A4 (state model
philosophy), §Concurrency notes; `enocean-async-notes.md` (upstream API).

## Goals (in scope for Phase 0)

- Connect to a serial dongle, expose received raw telegrams as an async
  iterator, expose connection-state changes as a separate async iterator,
  expose queue-overflow warnings as a third async iterator, and accept
  outgoing ESP3 packets via `send()`.
- Own the reconnect loop with exponential backoff + jitter; transitions
  reflected in the state machine.
- Plug-replaceable with `FakeDongle` (Phase-0 test double) via a shared
  `Dongle` `Protocol`.

Out of scope (deferred): high-level `send_command`, device registry,
teach-in, EEP decoding, multi-dongle.

## Module layout

```
src/enocean_async_tui/dongle/
    __init__.py          # re-exports DongleService, FakeDongle, RawTelegram, State, ...
    protocol.py          # Dongle Protocol; State enum; warning / change dataclasses
    types.py             # RawTelegram dataclass
    service.py           # DongleService (this spec)
    fake.py              # FakeDongle (see fake-dongle.md)
```

## Public types (in `dongle/protocol.py` and `dongle/types.py`)

```python
class State(StrEnum):
    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSED = "closed"

@dataclass(frozen=True, slots=True)
class StateChange:
    old: State
    new: State
    at: datetime          # tz-aware, UTC

@dataclass(frozen=True, slots=True)
class QueueOverflowWarning:
    dropped_count: int    # cumulative since last warning
    since: datetime       # window start, tz-aware UTC

@dataclass(frozen=True, slots=True)
class RawTelegram:
    raw: ERP1Telegram     # upstream object, untouched
    received_at: datetime # tz-aware UTC; stamped when callback fires

    @property
    def rssi_dbm(self) -> int | None: ...   # passthrough to raw.rssi (None if 0xFF)
    @property
    def sender(self) -> EURID | BaseAddress: ...   # passthrough
    @property
    def rorg(self) -> RORG: ...                    # passthrough
    @property
    def payload(self) -> bytes: ...                # passthrough to raw.telegram_data
```

`RawTelegram` adds **only** what upstream lacks (`received_at`). Everything
else is exposed via passthrough properties so call sites have one shape to
work with — verified against `ERP1Telegram` in `enocean-async-notes.md`.

## `Dongle` Protocol (shared with `FakeDongle`)

```python
class Dongle(Protocol):
    @property
    def state(self) -> State: ...
    async def connect(self) -> None: ...
    async def aclose(self) -> None: ...
    async def send(self, packet: ESP3Packet) -> SendResult: ...
    def telegrams(self) -> AsyncIterator[RawTelegram]: ...
    def state_changes(self) -> AsyncIterator[StateChange]: ...
    def warnings(self) -> AsyncIterator[QueueOverflowWarning]: ...
```

`telegrams()`, `state_changes()`, `warnings()` each return a **fresh**
async iterator on each call, backed by an independent bounded
`asyncio.Queue`. Multiple consumers therefore each get their own stream
without coordination — late joiners see only events from subscription
onward (no replay).

## `DongleService` lifecycle

### State machine

```
        connect()
  IDLE ──────────► CONNECTING ──ok──► CONNECTED ──port lost──► RECONNECTING
                       │ fail                                       │
                       └──────────────────► RECONNECTING ◄──────────┘
                                                  │
                                          aclose() │ │ ok
                                                  ▼ ▼
                                                CLOSED   ◄── from any state on aclose()
```

Transition table:

| From | Event | To | Side effect |
|---|---|---|---|
| IDLE | `connect()` invoked | CONNECTING | Instantiate `Gateway(port)`; register callbacks; await `start(auto_reconnect=False)`. |
| CONNECTING | `start()` returned | CONNECTED | Push initial `StateChange` to subscribers. |
| CONNECTING | `start()` raised `ConnectionError`/`OSError` | RECONNECTING | Schedule next attempt via backoff. Log error at WARNING. |
| CONNECTED | callback indicates port loss (e.g. `connection_status == "disconnected"` observation, or pyserial transport closed) | RECONNECTING | Call `gateway.stop()`. Schedule next attempt via backoff. |
| RECONNECTING | backoff timer fires | CONNECTING | Same as IDLE → CONNECTING but with attempt counter incremented. |
| any | `aclose()` invoked | CLOSED | Cancel reconnect timer; call `gateway.stop()` if non-None; close all subscriber queues with sentinel; further calls are no-ops. |

`state` property always reflects the current node. The transition
sentinel `(old, new, at)` is published to every active `state_changes()`
iterator.

### Backoff (locked by Phase-0 spec)

Module-level constants in `dongle/service.py` so tests can monkey-patch:

```python
INITIAL_DELAY_S: float = 0.5
MAX_DELAY_S: float = 30.0
MULTIPLIER: float = 2.0
JITTER: float = 0.1   # ±10 %
```

Computed delay for attempt `n` (zero-based):

```python
base = min(INITIAL_DELAY_S * MULTIPLIER ** n, MAX_DELAY_S)
delay = base * uniform(1 - JITTER, 1 + JITTER)
```

Attempt counter resets to 0 on a successful CONNECTED transition.

## Telegram queue (architecture A1)

- Bounded `asyncio.Queue[RawTelegram]`, default capacity **256**.
- On overflow: drop the oldest item (use `queue.get_nowait()` then
  `put_nowait(new)`), increment a private `_overflow_counter`, and on the
  next overflow within the same 1 s window keep counting; emit a
  `QueueOverflowWarning(dropped_count, since)` to the warnings stream
  whenever a window closes with `dropped_count > 0`.
- Capacity is `dongle/service.py` module constant `TELEGRAM_QUEUE_SIZE = 256`.

Each `telegrams()` call yields its own queue; each consumer therefore has
its own overflow accounting (rare in practice — one consumer in Phase 0).

## `send()`

```python
async def send(self, packet: ESP3Packet) -> SendResult:
    """Forward to Gateway.send_esp3_packet. Raises ConnectionError if state is not CONNECTED."""
```

- If `state != CONNECTED`, raise `ConnectionError` immediately. Do not queue.
- Upstream's lock serialises concurrent senders; we do not add another.
- Timeout follows upstream behaviour (≤ 500 ms wait for response, then
  returns `SendResult(response=None, ...)`).

Higher-level `send_command(...)` is **not** in Phase 0.

## `aclose()`

- Idempotent: calling twice is a no-op on the second call.
- Cancels the reconnect task if pending.
- Calls `gateway.stop()` (synchronous upstream).
- Closes every subscriber queue by enqueueing a sentinel; the async
  iterators detect it and `StopAsyncIteration`.
- Final state is `CLOSED`. No further `connect()` allowed (raise
  `RuntimeError("DongleService is closed")`).

`async with DongleService(port) as service:` is supported and equivalent
to `connect()` on entry, `aclose()` on exit. Tests use this form.

## Logging

- Logger name: `enocean_async_tui.dongle`.
- INFO: state transitions (one line each).
- WARNING: connection failures, overflow events.
- DEBUG: every received telegram (sender + RORG only — full payload at
  TRACE-equivalent if we ever add it; not in Phase 0).
- ERROR: only for unexpected exceptions in the reconnect loop.

## Tests (Phase-0 layer pyramid)

Architecture §A5 mandates three layers; with no decoders yet, layer 1 (decoder
unit tests) is N/A. Phase 0 has:

1. **Service unit tests** (`tests/dongle/test_service.py`). Drive
   `DongleService` against a mocked `Gateway`. Scenarios:
   - `connect()` happy path — state goes IDLE → CONNECTING → CONNECTED;
     a `StateChange(IDLE, CONNECTING, ...)` and `(CONNECTING, CONNECTED,
     ...)` arrive on `state_changes()`.
   - `connect()` failure → enters RECONNECTING, backoff timer fires,
     succeeds on attempt 2.
   - Telegram callback → `RawTelegram` arrives on `telegrams()` with
     `received_at` populated and `rssi_dbm` matching upstream.
   - Queue overflow — push 300 telegrams faster than consumer reads;
     assert exactly one `QueueOverflowWarning` with `dropped_count == 44`.
   - `send()` while disconnected → `ConnectionError`.
   - `aclose()` from CONNECTED → state CLOSED, all iterators terminate.
   - `aclose()` is idempotent.
2. **Pilot UI test for state propagation** (`tests/test_app.py`).
   Boot the Textual app with a fake dongle, drive it through CONNECTING →
   CONNECTED → RECONNECTING, assert the header status string changes (see
   `app-shell.md`).

## Definition of done

- All scenarios above are green.
- Coverage of `dongle/service.py` ≥ 90 % line, ≥ 80 % branch (pulls the
  package average above the 80 % gate).
- `mypy --strict` clean.
- Manual smoke: `uv run enocean-tui --port /dev/ttyUSB0` (or non-existent
  port) opens the TUI and the header reflects the right state.
