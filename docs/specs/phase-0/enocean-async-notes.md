# `enocean-async` upstream notes (v0.13.1)

Read-only research on the upstream library so the rest of the Phase-0 spec
cites real names, not invented ones. Update on dependency bumps.

## Package facts

- Package name: `enocean_async` (not the older synchronous `enocean`).
- Installed version: `0.13.1`. `__version__` exported from
  `enocean_async/__init__.py`.
- Concurrency: pure asyncio over `pyserial-asyncio-fast` (no threads).
  Callbacks are dispatched via `loop.call_soon(cb, *args)` — same loop, no
  thread-safety glue needed.
- Submodules used by Phase 0: `gateway`, `protocol.erp1`, `protocol.esp3`,
  `address`. Higher-level `eep`, `semantics`, `device` are out of scope until
  Phase 2+.

## Main class — `Gateway`

```python
from enocean_async import Gateway

gateway = Gateway(port: str, baudrate: int = 57600)
```

Phase-0-relevant members:

| Member | Signature / type | Notes |
|---|---|---|
| `start` | `async def start(self, auto_reconnect: bool = True) -> None` | Opens serial, starts ESP3 reader, fetches base ID + version. Raises `ConnectionError` on failure. **We pass `auto_reconnect=False`** — see below. |
| `stop` | `def stop(self) -> None` | Synchronous. Cancels reconnect / learning tasks, closes transport. Idempotent. |
| `is_connected` | `bool` (property) | True iff transport is open and connection_status == "connected". |
| `add_erp1_received_callback` | `(cb: Callable[[ERP1Telegram], None], sender_filter: SenderAddress \| None = None) -> None` | **Phase-0 receive hook.** Fires for every parsed ERP1 telegram, before any EEP decoding. |
| `add_observation_callback` | `(cb: Callable[[Observation], None]) -> None` | Higher-level; emits `connection_status` observations among others. We subscribe **only for connection-status changes**. |
| `send_esp3_packet` | `async def (packet: ESP3Packet) -> SendResult` | **Phase-0 send.** Serialised by an internal lock; waits ≤ 500 ms for response. |
| `send_command` | `async def (destination, command, sender=None) -> SendResult` | Higher-level; requires `add_device(...)` first. **Out of scope for Phase 0** (devices land in Phase 2). |

There is **no async iterator** over telegrams upstream. `DongleService.telegrams()`
adapts the callback into one via a bounded queue (architecture §A1).

## Why `auto_reconnect=False`

Upstream's auto-reconnect retries every 5 s linearly for up to 1 hour. The
roadmap §Phase 0 DoD calls for "reconnecting with backoff" and the spec
locks 0.5 s → 30 s exponential with jitter. Two reconnect strategies
fighting each other is a bug source, so:

- We invoke `Gateway.start(auto_reconnect=False)`.
- `DongleService` owns the reconnect loop, applies our backoff, and calls
  `Gateway.stop()` + reinstantiates a fresh `Gateway` between attempts (the
  upstream object isn't designed for restart in place).

If a future profiling pass shows our loop is wasteful, we revisit by
enabling upstream auto_reconnect and listening to `connection_status`
observations only — but not in Phase 0.

## Telegram type — `ERP1Telegram`

Defined in `enocean_async.protocol.erp1.telegram`:

```python
@dataclass
class ERP1Telegram:
    rorg: RORG                     # enum: RPS / 1BS / 4BS / VLD / ...
    telegram_data: bytes           # 1–14 byte payload
    sender: EURID | BaseAddress    # 32-bit source address
    status: int = 0x00
    sub_tel_num: int | None = 0x03
    rssi: int | None = 0xFF        # signal strength, dBm (negative); 0xFF == "unknown"
    sec_level: int | None = None
    destination: EURID | BroadcastAddress | None = None
```

Field-by-field check against our planned `RawTelegram` wrapper:

| Wrapper candidate field | Already on upstream? | Verdict |
|---|---|---|
| `received_at: datetime` | No (semantic layer adds `Observation.timestamp` *after* decoding, but the raw telegram itself carries no arrival time). | **Add to wrapper.** Stamped at the moment `add_erp1_received_callback` fires. |
| `rssi_dbm: int` | Yes — `ERP1Telegram.rssi`. | **Do not duplicate.** Wrapper exposes it via passthrough property only. |

→ The wrapper is therefore minimal:

```python
@dataclass(frozen=True, slots=True)
class RawTelegram:
    raw: ERP1Telegram
    received_at: datetime
    # rssi_dbm, sender, rorg, telegram_data are read-through to self.raw
```

Convenience read-through properties (`@property def rssi_dbm(self) -> int | None: return self.raw.rssi`) keep the public API symmetrical without storing redundant fields.

## Connection lifecycle observations

`add_observation_callback` emits `Observation` objects with various
`entity` strings. The one we care about is `entity == "connection_status"`,
which carries `Observable.CONNECTION_STATUS` valued
`"connected" | "disconnected" | "reconnecting"`. Upstream replays the
current status to a freshly registered callback if the base ID is already
known.

Phase 0 uses these observations only to **log** what upstream thinks the
state is; the authoritative state machine lives in `DongleService`
(because we own reconnect, not upstream). This avoids two sources of truth.

## Exceptions

Upstream raises:

- `ConnectionError` — `start()` cannot open the port; `fetch_base_id()` /
  `fetch_version_info()` / `change_base_id()` called when not connected.
- `ValueError` — invalid arguments to device / learning / send_command APIs.
  Out of scope for Phase 0 since we never call those.
- `BaseIDChangeError` — `change_base_id()` rejected by the module. Out of
  scope.
- Parse errors (`ERP1ParseError`) are caught upstream, logged at debug, and
  swallowed — they do not surface to callbacks.

Phase 0 only needs to catch `ConnectionError` from `Gateway.start()` (and
`OSError` / `serial.SerialException` that may bubble through from
`pyserial-asyncio-fast` on transient USB hiccups; we treat them as
"disconnected, schedule reconnect").

## Canonical Phase-0 usage sketch

Embedded inside `DongleService`, roughly:

```python
gateway = Gateway(port=settings.port)
gateway.add_erp1_received_callback(self._on_erp1)           # → queue
gateway.add_observation_callback(self._on_observation)      # → log only
try:
    await gateway.start(auto_reconnect=False)
except ConnectionError:
    self._set_state(State.DISCONNECTED)
    self._schedule_reconnect()
```

`_on_erp1` wraps the telegram with `received_at = datetime.now(tz=UTC)` and
puts it into the bounded `asyncio.Queue` consumed by `telegrams()`.

## Open verifications for the implementer

These are facts the spec assumes; the first failing test in Phase 0 should
prove them:

1. `Gateway.start(auto_reconnect=False)` raises `ConnectionError` synchronously
   (well, via `await`) when the port is missing — it does not silently retry.
2. `Gateway.stop()` after a failed `start()` is safe (idempotent).
3. The ERP1 callback fires **inside the event loop** (`call_soon`), so
   pushing into an `asyncio.Queue` from the callback body is correct
   without `loop.call_soon_threadsafe`.
4. `ERP1Telegram.rssi` is `None` (or `0xFF`) when the dongle didn't supply
   it; we surface that as `None` from `RawTelegram.rssi_dbm`.

If any of these turn out to be wrong, fix the spec, not the test.
