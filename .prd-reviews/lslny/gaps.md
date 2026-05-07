# Missing Requirements

## Summary

The PRD covers Phase 1 (Sniffer MVP) with unusual clarity — the non-goals list
is sharp, the open questions are honest, and the test plan is concrete. However,
several requirements are completely absent and would cause implementation
surprises or user-facing failures if left unresolved.

The most urgent gap is structural: Phase 0.5 (frame capture tool) is called out
in the feature description but is entirely absent from the PRD. Everything in
the document describes Phase 1 only. Beyond that, a handful of concrete
behavioral specifications are missing — pause buffer memory bounds, FakeDongle
fixture format, timestamp timezone, and auto-scroll UX — that an implementer
will have to invent on the spot without guidance.

---

## Findings

### Critical Gaps / Questions

**1. Phase 0.5 (frame capture tool) has zero specification**

The feature description is "Spec and implement Phase 0.5 (frame capture tool)
and Phase 1 (Sniffer MVP)." The PRD covers Phase 1 in detail. Phase 0.5 is
never mentioned anywhere in the document — no problem statement, no goals, no
user stories, no technical approach, no test plan.

- Why this matters: implementation cannot start on Phase 0.5. It is a complete
  blank.
- Suggested question: What exactly is the Phase 0.5 frame capture tool? Is it
  a standalone CLI (`enocean-capture`), a library component, or a mode of the
  TUI? What does it produce (stdout, file, both)? What is its relationship to
  the FakeDongle recording format (`telegram_hex` / `t_offset_ms` JSONL)?

---

**2. Pause buffer memory bound is unspecified — "no data lost" is overclaimed**

Goal #4 states "no data lost" while paused. The Rough Approach proposes a local
`deque` in the worker for buffering. That deque is unbounded. The DongleService
queue is capped at 256 (already implemented as `TELEGRAM_QUEUE_SIZE`), but the
PRD's pause buffer is a separate structure that grows without limit for the
duration of the pause.

- Why this matters: an active EnOcean installation (office building, smart home
  with many devices) can produce tens of telegrams per second. A 10-minute
  pause at 10 telegrams/second = 6,000 buffered entries. The PRD says "no data
  lost" but doesn't define a cap, so implementers must invent one.
- Suggested question: What is the maximum size of the pause buffer? Should the
  UI show how many telegrams are queued? What should happen when the buffer is
  full — drop oldest, drop newest, or disable further pausing?

---

**3. FakeDongle recording fixture for Scenario C is unspecified**

Scenario C requires "replayed telegrams from a recorded session fixture" when
running without hardware. The Phase 0 code (`FakeDongle(realtime=True)` with no
`recording` parameter) creates a silent dongle that emits nothing. For Scenario
C to work, there must be a bundled fixture file shipped with the package.

The FakeDongle recording format is already implemented (JSONL lines with
`telegram_hex`, `rssi_dbm`, `t_offset_ms`) but is nowhere documented in the
PRD.

- Why this matters: without a bundled fixture, `enocean-tui` in fake-dongle
  mode shows a blank sniffer — Scenario C is broken out of the box.
- Suggested questions: Where does the bundled fixture file live in the project
  (`src/`, `tests/fixtures/`, `data/`)? What recording content should it have?
  Is the fixture format (JSONL) considered a stable public format or an
  internal detail? Should the fixture loop when exhausted, or show an
  "end of recording" state?

---

**4. End-of-replay behavior is unspecified**

When `FakeDongle._replay_loop` exhausts the recording, it returns silently. The
dongle remains `CONNECTED` but emits no more telegrams. The UI would show a
frozen log with no indication that replay has ended. There is no "end of
recording" event in the `Dongle` protocol.

- Why this matters: a demo user (Scenario C) would see the sniffer go silent
  mid-demo with no explanation.
- Suggested question: Should replay loop continuously? Should the UI show "End
  of recording — N telegrams replayed"? Should the dongle transition to a new
  state (e.g., a `REPLAY_COMPLETE` state, or back to `RECONNECTING`)?

---

**5. Auto-scroll behavior is unspecified**

A live scrolling log has a fundamental UX fork: does new content auto-scroll to
the bottom even if the user has scrolled up to read earlier entries? The PRD
describes a `RichLog` widget but doesn't specify scroll behavior.

- Why this matters: this decision affects both implementation and user
  experience significantly. Auto-scroll that fights the user's manual scroll is
  one of the most common TUI annoyances.
- Suggested question: Should the log auto-scroll to the bottom on every new
  entry? Or should it lock to the user's scroll position and show a "new
  entries below" indicator? Should pressing `End` resume auto-scroll?

---

### Important Considerations

**6. Timestamp timezone is unspecified**

`DongleService` and `FakeDongle` both stamp telegrams with
`datetime.now(tz=UTC)`. The PRD's proposed log format (`14:23:01.042`) shows
local-time format but doesn't specify UTC vs. local. Users debugging across
timezones (or after midnight) will get different behavior depending on what the
implementer chooses.

- Suggested question: Should log timestamps be displayed in local time or UTC?
  If local time, how should DST transitions be handled in a long-running session?

---

**7. Filter input validation behavior is unspecified**

Open Question #5 proposes single-sender-ID filtering via "8 hex digits." The
following cases are unaddressed:

- Input shorter than 8 characters (partial match or error?)
- Invalid hex characters typed mid-entry (`G`, `X`, etc.)
- Case sensitivity (`abcd1234` vs `ABCD1234`)
- `0x` prefix accepted or rejected?
- Live filtering as the user types, or only on Enter?

Without specifying these, each will be invented independently by the
implementer.

---

**8. RSSI "unknown" display is unspecified**

`RawTelegram.rssi_dbm` returns `None` when the dongle reports `0xFF` (unknown).
The PRD log format shows `RSSI -62 dBm` but doesn't specify what to render when
RSSI is unknown. This happens in practice (some telegram types don't carry RSSI).

- Suggested question: Display `RSSI –` / `RSSI n/a` / omit the field?

---

**9. QueueOverflowWarning integration with Phase 1 sniffer is unspecified**

`QueueOverflowWarning` is already implemented and Phase 0 handles it via
`self.notify(...)` (Textual toast). Phase 1 doesn't address whether overflow
warnings should also appear as entries in the `RichLog` (so they're visible in
context) or continue only as toasts. This is especially relevant when paused —
a toast may disappear before the user unpauses and notices that data was lost.

---

**10. Platform-specific port discovery is absent**

`DEFAULT_PORT = "/dev/ttyUSB0"` works on Linux. macOS dongles appear at
`/dev/tty.usbserial-*` or `/dev/cu.usbmodem*`. Windows uses `COM3` or similar.
The PRD targets "developers and makers with a laptop" but gives no guidance on
cross-platform usage.

The "demo-able in 60 seconds" constraint collides with the reality that a macOS
user running `enocean-tui` without `--port` will connect to a non-existent
Linux path and be dropped into fake-dongle mode with no clear explanation.

- Suggested question: Is multi-platform support in scope for Phase 1? If yes,
  should the app attempt to auto-detect the dongle port before prompting for the
  fake-dongle fallback?

---

**11. Serial port permission errors are not distinguished from "no dongle"**

`DongleService._attempt_connect` catches `(ConnectionError, OSError)` and
schedules a reconnect. On Linux, the most common failure for first-time users
is a permission error (`EACCES` — user not in `dialout` group). This is
indistinguishable from "dongle not plugged in" in the current error path.

The FallbackModal says "Couldn't open serial port." A permission error requires
a different fix (add user to group) than a missing dongle (plug it in). The PRD
doesn't address error message specificity.

---

**12. Signal handling / graceful shutdown is unspecified**

The PRD specifies `q` to quit but doesn't address SIGINT (Ctrl+C) or SIGTERM.
An ungraceful exit that doesn't call `DongleService.aclose()` can leave the
serial port in a bad state. Textual handles SIGINT by default, but the
interaction with the dongle cleanup lifecycle is unspecified.

---

**13. Log line format for multi-byte payloads is unspecified**

The example log line shows `70` as the payload (one byte, decimal or hex?). VLD
telegrams can carry up to 14+ bytes. The PRD doesn't specify:

- Format: hex bytes (`A5 00 14 08`) or full hex string (`A500140808`)?
- Truncation: show all bytes or truncate at N bytes with `…`?
- The `70` in the example appears to be hex `0x70` — but it's unlabeled

---

### Observations

**14. `sender` type edge cases not addressed**

`RawTelegram.sender` is typed as `EURID | BaseAddress`. The filter UI assumes
an 8-hex-digit EURID. For telegrams with a `BaseAddress` sender, the hex
representation may differ. The PRD implicitly assumes all senders are EURIDs.

**15. Concurrent instance protection not addressed**

Two `enocean-tui` instances targeting the same serial port will race. Serial
ports are exclusive on most OSes. No port lock-file or friendly error message
is specified. Low priority for Phase 1 but worth a non-goal acknowledgment.

**16. Non-TTY / piped execution not addressed**

Running `enocean-tui | tee log.txt` or inside Docker without a TTY will cause
Textual to fail in unexpected ways. Not even acknowledged as a non-goal.

**17. Accessibility is completely absent**

No screen reader, no color-blind alternative, no high-contrast mode — not even
a non-goal acknowledgment. For a developer tool this is low urgency, but the
PRD should at least acknowledge it.

---

## Confidence Assessment

**Medium.** The Phase 1 requirements are largely well-defined — the non-goals
are unusually precise, the open questions are honest, and the test plan is
concrete enough to implement from. The seven open questions in the PRD itself
acknowledge the most cosmetic gaps (RSSI icon, log format, pause UX) and are
close to resolvable without blocking implementation.

What drops this to Medium is: (1) Phase 0.5 is completely absent — that's a
missing phase, not a missing detail; (2) the FakeDongle fixture requirement for
Scenario C has no specification anywhere; and (3) the pause buffer memory bound
needs a number before implementation starts. Fix those three and the PRD is
strong enough to build from.
