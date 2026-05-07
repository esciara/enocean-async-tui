# Design: Phase 1 — Sniffer MVP

**PRD:** `.prd-reviews/sniffer-mvp/prd-draft.md`
**Status:** Draft (synthesized from PRD + clarifications; pending alignment review)

---

## 1. Problem & Scope

Phase 1 extends the Phase 0 app shell to deliver a live EnOcean telegram sniffer
with pause/resume, sender-ID filter, and clear — the first demo-able product.
Phase 0 components (DongleService, FakeDongle, Settings, app shell) are **fixed**;
Phase 1 adds only. No decoding, no device registry, no teach-in.

---

## 2. Goals Recap (from PRD clarifications)

| # | Goal | Notes |
|---|------|-------|
| 1 | Live scrolling log; telegrams appear with ≤100 ms display latency | Not cold-start target; latency from receive to screen |
| 2 | Log line: `YYYY-MM-DDTHH:MM:SS.mmm  0xABCD1234  RPS (0xF6)  <hex-payload>  RSSI -62 dBm` | ISO 8601 ts, 0x-prefix ID, name+hex RORG, full payload hex, dBm |
| 3 | Header: title, dongle status, port, base ID (`–` in Phase 1) | Base ID deferred to Phase 2 |
| 4 | Keys: q quit · c clear · p pause/resume · f filter | Pause buffer = bounded deque 256; overflow drops oldest, shows counter |
| 5 | Auto-reconnect continues to work | DongleService handles reconnect; sniffer worker re-subscribes |
| 6 | FakeDongle replay works in sniffer view | No hardware required for demo |
| 7 | Integration + UI Pilot tests pass | See §6 |
| 8 | Coverage ≥ 80%; CI green | |

---

## 3. Architecture

```
App (Textual)
├── Header widget           ← extend: port + base-ID fields
├── SnifferScreen           ← new (replaces placeholder)
│   ├── RichLog widget      ← Textual built-in; max_lines=10_000
│   └── FilterInput widget  ← inline Input, hidden until 'f' pressed
└── Footer widget           ← extend: q/c/p/f key hints
```

### 3.1 SnifferWorker

File: `src/enocean_async_tui/ui/workers/sniffer.py`

```python
class SnifferWorker:
    """Textual @work coroutine; iterates DongleService.telegrams().

    Pause: sets asyncio.Event; buffered telegrams accumulate in a
    collections.deque(maxlen=256). On resume, flushes buffer then
    re-enters normal iteration.

    'c' while paused: clears both the RichLog AND the deque.
    """
```

Posts `TelegramReceived(telegram: RawTelegram)` Textual messages to App.

### 3.2 Telegram data model

```python
@dataclass
class FormattedTelegram:
    timestamp: str     # ISO 8601 with ms: "2026-05-07T14:23:01.042"
    sender_id: str     # "0xABCD1234"
    rorg_name: str     # "RPS (0xF6)"
    payload_hex: str   # full hex string, no 0x prefix
    rssi_dbm: int      # e.g. -62
    raw: RawTelegram
```

### 3.3 Filter model

- Stored as `filter_id: int | None` on SnifferScreen.
- Filter is **retroactive**: re-renders entire log from in-memory `_buffer: list[FormattedTelegram]` (capped at 10 000 entries, same as `max_lines`).
- Applied **on Enter**, not live. Input shows "pending" visual state while typing.
- Filter input accepts `0x` prefix (strips it before matching).
- `f` again or `Escape` clears filter; full log re-renders.

### 3.4 Pause / Clear semantics

- **Pause on** (`p`): `_paused = True`; new telegrams go to `_pause_buffer: deque[FormattedTelegram](maxlen=256)`.
- **Overflow**: oldest entry silently dropped; `_dropped_count` incremented; header or banner shows "N dropped".
- **Clear while paused** (`c`): `RichLog.clear()` + `_pause_buffer.clear()` + `_buffer.clear()` + `_dropped_count = 0`.
- **Clear while running** (`c`): `RichLog.clear()` + `_buffer.clear()`.
- **Pause off** (`p`): flush `_pause_buffer` to `_buffer` and `RichLog` in order, then resume normal streaming.

---

## 4. API Design

### 4.1 Public interface additions (Phase 1 only)

```python
# TelegramReceived Textual message
class TelegramReceived(Message):
    telegram: RawTelegram

# SnifferWorker
class SnifferWorker:
    async def run(self) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def clear_buffer(self) -> None: ...
```

No changes to `DongleService`, `FakeDongle`, or `Settings` public APIs.

### 4.2 App entry point

`uv run enocean-tui [--port /dev/ttyUSB0] [--fake]`

- No `--port` or port not found → auto-discover connected dongles; if none, offer FakeDongle modal (existing Phase 0 flow).
- Phase 1 adds **auto-discovery**: scan serial ports for EnOcean dongles, connect automatically or present options.

---

## 5. Implementation Tasks (ordered)

### Phase 1-A: Sniffer worker (core plumbing)

1. `src/enocean_async_tui/ui/workers/__init__.py` — create package
2. `src/enocean_async_tui/ui/workers/sniffer.py` — `SnifferWorker` class
   - `async def run()`: iterates `DongleService.telegrams()`
   - Pause buffer (deque maxlen=256) + asyncio Event
   - Posts `TelegramReceived` to app
3. `src/enocean_async_tui/ui/messages.py` — `TelegramReceived` message dataclass
4. Wire into `App.on_mount`: start SnifferWorker alongside existing state subscriber

### Phase 1-B: Sniffer screen / log display

5. `src/enocean_async_tui/ui/screens/sniffer.py` — `SnifferScreen`
   - `RichLog(max_lines=10_000, wrap=False)`
   - `_buffer: list[FormattedTelegram]` for retroactive filter
   - Handles `TelegramReceived` → format → apply filter → append to log
6. `src/enocean_async_tui/ui/formatters.py` — `format_telegram(t: RawTelegram) -> FormattedTelegram`
   - Timestamp: `datetime.now().isoformat(timespec="milliseconds")`
   - Sender ID: `f"0x{t.sender_id:08X}"`
   - RORG: name lookup + `f"{name} (0x{rorg_byte:02X})"`
   - Payload: `t.data.hex().upper()` (full hex, no truncation)
   - RSSI: integer dBm from `t.rssi`

### Phase 1-C: Key bindings + filter

7. `q` binding → `app.exit()`
8. `c` binding → `screen.clear_log()`
9. `p` binding → `screen.toggle_pause()`
10. `f` binding → show `FilterInput`; on Enter → apply filter; on Escape → clear filter

### Phase 1-D: Header extension

11. Extend existing Header widget to add port (from Settings) and base-ID (`–`)
12. Dongle status already wired in Phase 0; extend to update port label on connect

### Phase 1-E: Auto-discovery

13. When no `--port` given (or port not found), scan serial ports for EnOcean dongles
14. If exactly one found: auto-connect
15. If multiple: present selection modal
16. If none: existing FakeDongle modal flow (Phase 0)

---

## 6. Test Plan

### Unit tests

| Test | File | Key assertion |
|------|------|---------------|
| `test_format_telegram` | `tests/unit/test_formatters.py` | Log line matches exact format spec |
| `test_rorg_lookup` | `tests/unit/test_formatters.py` | All known RORGs produce correct name |
| `test_pause_buffer_overflow` | `tests/unit/test_sniffer_worker.py` | 257th entry drops oldest, counter increments |
| `test_clear_while_paused` | `tests/unit/test_sniffer_worker.py` | Both log buffer and pause buffer empty after clear |

### Integration tests (FakeDongle + Textual Pilot)

| Test | Scenario | Assertion |
|------|----------|-----------|
| `test_live_display` | FakeDongle replays 3 telegrams | All 3 lines appear in RichLog |
| `test_pause_resume` | Replay 2, pause, replay 2 more, resume | 4 lines total; none lost |
| `test_pause_overflow` | Pause, replay 257 telegrams | 256 lines visible; overflow counter shows 1 |
| `test_clear_running` | Populate log, press `c` | Log empty |
| `test_clear_paused` | Pause, queue 5, press `c`, resume | Log remains empty after resume |
| `test_filter_retroactive` | Replay 2 IDs, apply filter for ID-A | Only ID-A lines in RichLog |
| `test_filter_enter` | Type partial ID, assert no change; press Enter | Log updates only on Enter |
| `test_filter_clear` | Apply filter, press Escape | Full log re-renders |

---

## 7. Open Questions (resolved from PRD clarifications)

| OQ | Decision |
|----|----------|
| Log retention | 10 000 lines (`RichLog(max_lines=10_000)`) |
| Base ID | `–` throughout Phase 1; retrieved in Phase 2 |
| RSSI display | Raw dBm only (no icons) |
| Pause UX | Banner: "PAUSED — N queued" (+ "N dropped" if overflow) |
| Filter scope | Single sender ID; 8 hex digits; `0x` prefix accepted and stripped |
| RORG display | Name + hex: `RPS (0xF6)` |
| Log line format | `YYYY-MM-DDTHH:MM:SS.mmm  0xABCD1234  RPS (0xF6)  <payload-hex>  RSSI -62 dBm` |
| Port not found | Auto-discover first; then FakeDongle modal if no dongle found |
| 100 ms goal | Display latency (receive-to-screen), not cold-start |

---

## 8. Non-Goals (confirmed not in scope)

- Telegram decoding
- Device registry
- Teach-in flow
- Outgoing commands
- Multi-dongle support
- Structured file logging
- MQTT / remote access
- RORG / payload content filtering
- Base ID retrieval (`–` shown throughout Phase 1)

---

## 9. Dependencies

- **Phase 0 (fixed):** DongleService, FakeDongle, Settings, app shell
- **Python stdlib:** `collections.deque`, `asyncio.Event`, `datetime`
- **Textual built-ins:** `RichLog`, `Worker` / `@work`, `Input`
- **No new runtime dependencies**

---

## 10. Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Retroactive filter re-render slow for 10K entries | Medium | Only re-render on Enter; `RichLog.clear()` + batch append is fast |
| Pause buffer overflow misleads user | Low | Show dropped-count prominently in PAUSED banner |
| FakeDongle replay timing differs from real dongle | Low | Tests use FakeDongle explicitly; real dongle integration is manual |
| Textual Worker lifecycle vs asyncio Event interaction | Medium | Use `asyncio.Event` (not `threading.Event`); same event loop |
