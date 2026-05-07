# PRD: Phase 1 — Sniffer MVP (live EnOcean telegram log)

## Problem Statement

EnOcean is a battery-less wireless protocol used in smart home and building
automation. When setting up or debugging an EnOcean installation — teaching in
new devices, hunting phantom senders, diagnosing missed telegrams — there is no
lightweight, developer-friendly tool that lets you see raw traffic on the bus.
Wireshark has no EnOcean dissector. Home Assistant is heavyweight and opinionated.
The reference tools (Dolphin Studio, PCT14) are Windows-only and GUI-heavy.

A developer or maker who has a USB EnOcean dongle and a laptop should be able to
run one command and immediately see every telegram flying through the air, the way
`tcpdump` shows TCP packets. Right now that tool does not exist in the open-source
Python ecosystem.

**Who:** Developers, makers, home automation enthusiasts, system integrators who
work with EnOcean hardware.

**Why now:** Phase 0 ships the foundation (DongleService, FakeDongle, Settings,
app shell). Phase 1 is the first actually useful product to put in front of
users. Shipping something demo-able early validates the stack and gets real
usage feedback before we invest in device registries and decoders.

## Goals

1. A user can run `uv run enocean-tui --port /dev/ttyUSB0` and see a live,
   scrolling log of EnOcean telegrams within 100 ms of the command starting.
2. Each log line shows: timestamp, 32-bit sender ID (hex), RORG name
   (RPS / 1BS / 4BS / VLD / …), raw payload hex, and RSSI in dBm.
3. Header displays: app title, dongle status, serial port, dongle base ID.
4. Key bindings work reliably:
   - `q` — quit
   - `c` — clear the log
   - `p` — pause/resume (telegrams queue while paused, no data lost)
   - `f` — enter filter mode (show only a given sender ID)
5. Auto-reconnect from Phase 0 continues to work: unplugging the dongle
   moves status to "reconnecting", re-plugging resumes the live log without
   restarting the app.
6. FakeDongle replay path works: pressing a recorded switch replays correctly
   in the sniffer view, enabling demos without hardware.
7. All three test layers pass: decoder unit (n/a for Phase 1, no decoding),
   integration (DeviceManager or sniffer worker + FakeDongle), UI Pilot tests.
8. Coverage gate stays ≥ 80%. CI gate stays green.

## Non-Goals

- **No telegram decoding.** Payloads are shown raw (hex bytes). Mapping RORG +
  payload to human-readable values (temperature, button state, etc.) is Phase 3.
- **No device registry.** No persistence of sender IDs, names, or EEPs.
- **No teach-in flow.** That belongs to Phase 2.
- **No outgoing commands.** Sniffer is read-only.
- **No multi-dongle support.**
- **No structured file logging.** Plain display only; file logging is Phase 4.
- **No MQTT bridge or remote access.**
- **No filtering by RORG or payload content** — sender ID filter only.

## User Stories / Scenarios

**Scenario A — Debug a broken automation**
Alice's kitchen light stops responding to her rocker switch. She plugs in her
USB dongle, runs `enocean-tui`, and watches the log. She presses the switch
and sees a telegram with sender ID `0xABCD1234`. She presses `f`, enters
`ABCD1234`, and the log now shows only that device. She presses the switch
again — the telegram appears. The problem is not the switch; it must be
downstream.

**Scenario B — Identify an unknown device**
Bob inherits a house with unknown EnOcean devices. He opens `enocean-tui`
and walks through the rooms pressing buttons and opening doors. The log fills
up with sender IDs. He copies the IDs to a spreadsheet to map them later.

**Scenario C — Demo without hardware**
Carol is writing a talk about EnOcean. She has no dongle on her laptop. She
runs `enocean-tui` without `--port`; the app shows the "no dongle" modal and
she accepts "Fake dongle mode". The sniffer shows replayed telegrams from a
recorded session fixture.

**Scenario D — Pause and inspect**
Dave sees an interesting burst of telegrams. He presses `p` to pause. The
log freezes. He reads the entries carefully. He presses `p` again — the
queued telegrams flush into the log instantly. No telegrams were dropped
while paused (within the DongleService queue bound of 256).

## Constraints

- **Async-only.** The serial reader must stay a Textual Worker or asyncio
  task; no blocking I/O on the event loop thread.
- **Single event loop.** Textual and enocean-async share the same asyncio
  loop. No threads except `asyncio.to_thread` for blocking calls (none expected
  in Phase 1).
- **Phase 0 foundation is fixed.** DongleService public API, FakeDongle
  protocol, Settings fields, and app shell structure are not renegotiated in
  Phase 1. Additions only.
- **No new runtime dependencies without a clear reason.** The current stack
  (Textual, enocean-async) is sufficient for Phase 1.
- **TDD is non-negotiable.** Every feature is driven by a failing test first.
  No production code without a test that demanded it.
- **mypy strict must stay clean.** No `# type: ignore` escape hatches.
- **Demo-able in 60 seconds.** A first-time user can go from zero to live
  sniffer in under a minute.

## Open Questions

1. **Log retention.** How many lines should the `RichLog` hold before old
   entries are discarded? Unbounded growth will eventually cause memory/render
   issues on long-running sessions. Candidate: 10 000 lines, configurable.

2. **Base ID retrieval.** The dongle base ID is available via
   `enocean_async.Gateway` but requires a request telegram
   (`COMMON_COMMAND_RBASE`). Should Phase 1 issue that request on connect, or
   defer to Phase 2? (Impact: header shows "base ID: –" until resolved.)

3. **RSSI display.** Show raw dBm only, or add a signal-strength icon (●●●○○)?
   Icons add visual noise; dBm is more useful for debugging.

4. **Pause UX.** How should paused state be communicated? Options:
   a. Banner at the top of the log pane ("PAUSED — N queued")
   b. Header status change
   c. Footer key binding changes colour
   Option (a) is most discoverable.

5. **Filter UX.** Single sender ID at a time (simplest), or a set of IDs?
   Multi-filter is more powerful but makes the filter entry widget harder.
   Phase 1 scope: single ID, typed as 8 hex digits, cleared with `f` again or
   `Escape`.

6. **RORG name vs. hex.** Should RORG be shown as the protocol name (RPS, 1BS,
   4BS, VLD, …) or as raw hex (`0xF6`, `0xD5`, `0xA5`, `0xD2`)? Both?
   Proposal: name + hex in parentheses: `RPS (0xF6)`.

7. **Log line format.** Proposed:
   ```
   14:23:01.042  0xABCD1234  RPS (0xF6)  70  RSSI -62 dBm
   ```
   Is the column order right? Should payload be shown as full hex or truncated?

## Rough Approach

Phase 1 extends the Phase 0 app shell with minimal additions:

**Sniffer worker (`src/enocean_async_tui/ui/workers/sniffer.py`)**
- A Textual `Worker` (or `@work` coroutine) that iterates
  `DongleService.telegrams()`.
- On each `RawTelegram`, posts a `TelegramReceived` Textual message to the app.
- Pausing: worker checks a `threading.Event` (or asyncio-compatible flag) and
  buffers telegrams in a local `deque` while paused; flushes on resume.
- Worker is started in `App.on_mount` alongside the existing state-change
  subscriber.

**Sniffer screen / widget**
- Main pane is replaced with a `RichLog` widget (Textual built-in).
- App handles `TelegramReceived(telegram: RawTelegram)` → formats a line →
  appends to `RichLog`.
- Filter: held as `filter_id: int | None` on the app (or screen); 
  `TelegramReceived` handler skips non-matching entries when filter is active.
- `c` key → `rich_log.clear()`.

**Header extension**
- Add port (from Settings) to the header on connect.
- Add base ID (from dongle or `–` if unknown) after port.
- Status text already works from Phase 0; extend it if needed.

**Key bindings**
- `q`, `p`, `c` added to footer bindings.
- `f` opens an inline `Input` widget (or a modal) for filter entry; 
  Escape clears it.

**Tests**
- Integration: `FakeDongle` replays 3 telegrams; assert all 3 appear in the
  `RichLog` via Pilot.
- Pause: replay 2 telegrams, pause, replay 2 more, resume; assert 4 total.
- Filter: replay telegrams from 2 sender IDs; apply filter for one; 
  assert only matching lines visible.
- Clear: populate log, press `c`, assert log empty.

## Clarifications from Human Review

**Q1: Is "no data lost while paused" an absolute guarantee or capped at 256?**
A: Capped at 256 entries. The pause buffer is a bounded deque of 256. When full, the oldest entry is dropped to make room for the newest (ring-buffer semantics). A "N telegrams dropped while paused" counter is shown in the UI when overflow occurs.

**Q2: What happens when `c` (clear) is pressed while paused?**
A: `c` clears both the visible log AND the pause buffer. The user gets a clean slate — on resume, only telegrams received after unpausing will appear.

**Q3: Does the filter apply retroactively or only to new telegrams?**
A: Retroactive. When a filter is applied or changed, the entire log re-renders from an in-memory buffer of all received telegrams. Requires keeping all received telegrams in memory (up to the log retention bound).

**Q4: Does the filter apply on Enter or live on each keystroke?**
A: Apply on Enter. Show a "pending" visual state while the user is typing. Log re-renders only on Enter (or Escape to clear).

**Q5: What is the exact log line format?**
A: `2026-05-07T14:23:01.042  0xABCD1234  RPS (0xF6)  70  RSSI -62 dBm`
- Timestamp: ISO 8601 full datetime with millisecond precision (`YYYY-MM-DDTHH:MM:SS.mmm`)
- Sender ID: `0xABCD1234` (C-style hex with `0x` prefix)
- RORG: name + hex in parentheses `RPS (0xF6)`
- Payload: full hex string
- RSSI: dBm value
- Filter input: accepts `0x` prefix (strips it for matching)

**Q6: When `--port` is given but can't be opened, what does the UI show?**
A: Offer FakeDongle fallback (matching Scenario C). Additionally, Phase 1 should include auto-discovery of connected dongles — when no `--port` is specified (or the given port is not found), the app scans for available EnOcean dongles and either connects automatically or presents options.

**Q7: Is the "100 ms" startup target from process start or first dongle frame?**
A: Display latency — telegrams appear within 100 ms of being received by the app. This is not a cold-start target. Goal 1 should be reworded to: "A user can run `uv run enocean-tui --port /dev/ttyUSB0` and see a live, scrolling log of EnOcean telegrams with no perceptible lag between a telegram arriving and it appearing in the log."

**Q8: Is base ID retrieval (COMMON_COMMAND_RBASE) in scope for Phase 1?**
A: Deferred to Phase 2. The header shows `–` for base ID throughout Phase 1. Goal 3 amended: "Header displays: app title, dongle status, serial port, dongle base ID (shows `–` in Phase 1; retrieved in Phase 2)."
