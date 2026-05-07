# PRD Review: Phase 1 — Sniffer MVP (live EnOcean telegram log)

## Executive Summary

The Sniffer MVP PRD is unusually well-specified for a draft: non-goals are clearly stated, user
scenarios are concrete, and the TDD/mypy constraints show engineering discipline. The main risks
are a direct contradiction in the pause semantics (Goal 4 says "no data lost" but Rough Approach
caps the queue at 256), an unresolved filter interaction model (retroactive vs. prospective) that
is a 3× scope difference in implementation, and several Open Questions that remain proposals
rather than decisions. Overall readiness is **Medium** — implementation can start on the core
display path, but three binary decisions must be made before the first integration test is written.

---

## Before You Build: Critical Questions

### Pause Semantics

**Q1: Is "no data lost while paused" an absolute guarantee or "no data lost within a 256-entry burst"?**
- Why this matters: Goal 4 guarantees no data loss; Rough Approach caps the queue at 256.
  These are contradictory. Two engineers will implement this differently — one silently drops
  at 256, the other grows the buffer indefinitely.
- Found by: ambiguity (finding 1), requirements (finding 2), scope (finding 4)
- Suggested answer options:
  a. "No data lost" scoped to 256 entries; overflow silently drops oldest (simplest, honest)
  b. Unbounded deque; accept memory risk for long pauses (no data loss, more complex)
  c. Overflow shows a "N telegrams dropped while paused" counter in the UI

**Q2: What happens when the user presses `c` (clear) while paused?**
- Why this matters: The visible log clears but the pause buffer still holds queued telegrams;
  on resume, the "empty" log suddenly fills. Defined behavior prevents a bug-report cycle.
- Found by: scope (finding 6)
- Suggested answer options:
  a. `c` clears both the visible log AND the pause buffer (user gets a clean slate)
  b. `c` clears only the visible log; pause buffer flushes on resume (no data loss)

### Filter Model

**Q3: Does the filter apply retroactively (re-render existing log) or only to new telegrams?**
- Why this matters: Retroactive filtering requires a parallel in-memory buffer of all received
  telegrams and a full `RichLog` repopulate on filter change — a significantly larger scope than
  prospective-only filtering. Scenario A ("watches the log … presses f … log now shows only
  that device") implies retroactive, but the Rough Approach implies prospective.
- Found by: ambiguity (finding 2), feasibility (finding 4), scope (finding 3)
- Suggested answer options:
  a. Prospective-only: filter gates new telegrams, existing log unchanged (simpler, Phase 1 fits)
  b. Retroactive: full re-render on filter change (larger scope, matches Scenario A literally)

**Q4: Does the filter apply on Enter or character-by-character?**
- Why this matters: Live-filter requires checking the in-memory buffer on every keystroke;
  Enter-commit can defer the check. Undefined → untestable.
- Found by: ambiguity (finding 2)
- Suggested answer options:
  a. Apply on Enter; show "pending" state while typing
  b. Apply immediately on each keystroke (live filter)

### Log Line Format

**Q5: Decide the exact log line format before integration tests are written.**
- Why this matters: The Pilot test must look for a fixed string in `RichLog`. Any unresolved
  column order, separator, RORG format, or payload truncation means the test cannot be written.
  Open Question 7 proposes `14:23:01.042  0xABCD1234  RPS (0xF6)  70  RSSI -62 dBm` — is this
  the accepted format?
- Found by: ambiguity (finding 3 and 4), requirements (implied by test strategy)
- Sub-decisions needed:
  - **RORG:** name + hex `RPS (0xF6)`, hex only `0xF6`, or name only `RPS`?
  - **Sender ID:** `0xABCD1234` (C-style) or `ABCD1234` (bare hex)?
  - **Sender ID in filter:** does the filter accept the `0x` prefix or reject it?
  - **Payload:** full hex string, or truncated to N bytes with `…`?
  - **Timestamp:** millisecond precision `HH:MM:SS.mmm` or second-only?

### Error Handling

**Q6: When `--port /dev/ttyXXX` is given but the port does not exist or cannot be opened, what does the UI show?**
- Why this matters: This is the most common first-run failure. Without a spec, every engineer
  invents their own behavior. The decision also determines whether the "60 seconds to live
  sniffer" goal is achievable when the port is wrong.
- Found by: gaps (finding 1), gaps (finding 6)
- Suggested answer options:
  a. Error modal ("Port /dev/ttyXXX not found. Check connection and retry.") with quit option
  b. A log line with the error; app stays alive (user can unplug/replug)
  c. Automatic fallback offer to FakeDongle (matches Scenario C pattern)

### Startup Latency Target

**Q7: Is the "100 ms of the command starting" target measured from process start or from first dongle frame?**
- Why this matters: Python 3.14 + uv + serial init + Textual compose is 500–1500 ms in practice.
  If this is a hard CI gate measured from process start, it will fail. If it means "first telegram
  appears within 100 ms of the dongle being ready", it is achievable.
- Found by: feasibility (finding 1), requirements (finding 1)
- Suggested answer options:
  a. Aspirational / marketing copy — remove the 100 ms number from Goals; replace with "no
     perceptible lag between a telegram arriving and appearing in the log"
  b. Measured from first dongle frame ready; tested as an integration assertion with FakeDongle

### Base ID Scope Decision

**Q8: Is base ID retrieval (COMMON_COMMAND_RBASE) in scope for Phase 1 or deferred?**
- Why this matters: Goal 3 says "header displays dongle base ID" but Open Question 2 defers
  it. Retrieval requires an outgoing command and async response parsing — a small but non-trivial
  addition. If deferred, Goal 3 must be amended to "header shows `–` for base ID in Phase 1".
- Found by: scope (finding 1), ambiguity (finding 7)
- Suggested answer options:
  a. Defer to Phase 2; header shows `–` always in Phase 1 (simpler, no outgoing commands)
  b. Include in Phase 1; spec the async request/response handling

---

## Important But Non-Blocking

*(Implementation can start on the display core; these need resolution before the relevant feature is coded.)*

- **RSSI availability:** Verify that `enocean-async`'s telegram model exposes RSSI from the ESP3
  optional data section. If absent for some telegram types, define the fallback display value
  (`–` or `N/A`). File a blocker bead if RSSI is not exposed at all.
  *(feasibility finding 2, gaps finding 8)*

- **Pause indicator UX:** Open Question 4 lists three options (banner, header, footer). Decide
  before implementing pause; without a decision there is no testable acceptance criterion.
  Option (a) — banner "PAUSED — N queued" — is the most discoverable.
  *(ambiguity finding 6)*

- **`q` binding scope:** Does `q` quit when the filter `Input` widget has focus? Textual widget
  focus changes binding priority. Define: `q` always quits regardless of focused widget, OR
  `q` is consumed by the Input when focused and Escape is required first.
  *(gaps finding 4)*

- **FakeDongle fixture:** Goal 6 and Scenario C require a "recorded session fixture". Define
  the format (Python list of `RawTelegram`-compatible dicts? Binary ESP3 capture?) and commit
  a fixture file as part of Phase 1 scope.
  *(scope finding 2, requirements finding 7)*

- **`asyncio.Event` not `threading.Event`:** The Rough Approach mentions "threading.Event (or
  asyncio-compatible flag)". In an all-asyncio context, use `asyncio.Event` — `threading.Event`
  is unsafe to await and will block the event loop.
  *(feasibility finding 6)*

- **Unknown RORG handling:** What should the UI show for an RORG byte not in the known set
  (e.g., Smart ACK, MSC, SYS-EX frames)? Recommended: `UNK (0xXX)` — show all bytes, name
  unknown ones explicitly.
  *(gaps findings 2 and 3)*

- **RORG-to-name table:** Displaying `RPS (0xF6)` requires a mapping table. The PRD non-goals
  "no device registry" but a 15-entry RORG table is scope that should be acknowledged. Add
  "RORG-to-name table included in Phase 1 scope" to requirements.
  *(scope finding 5)*

- **Log retention bound:** Promote Open Question 1 to a requirement: `RichLog(max_lines=10_000)`
  as the default. Note: `RichLog` supports this natively — it is trivial to implement.
  *(requirements finding 4, feasibility observation)*

- **enocean-async version pin:** Confirm the version used in Phase 0 is the intended Phase 1
  version. Verify mypy strict compatibility (some async libraries have incomplete type stubs).
  *(feasibility observation, stakeholders finding 3)*

---

## Observations and Suggestions

- **Filter is the highest schedule risk.** The core sniffer (display, pause, clear) delivers
  Scenario A–D value without filter. If timeline is tight, filter could slip to Phase 1.1
  without loss of demo-ability. Decide prospective-only + Enter-commit to minimize scope.

- **Per-module coverage floor:** 80% project-wide could mask low coverage on new sniffer code
  if older modules carry the average. Consider `src/enocean_async_tui/ui/workers/` ≥ 90%.
  *(requirements finding 5)*

- **Platform serial port defaults:** The PRD uses `/dev/ttyUSB0` as example. macOS default is
  `/dev/cu.usbserial-*`; Windows is `COM3`. Define the default (or "no default — user must pass
  `--port`") per platform to support the "60 seconds" onboarding goal.
  *(gaps finding 5, stakeholders finding 2)*

- **Primary persona error verbosity:** System integrators want graceful silent recovery;
  developers want verbose tracebacks. Decide the default error verbosity before error-handling
  code is written. Recommendation: errors shown in the UI (log line or modal), not swallowed;
  tracebacks only with `--debug` flag.
  *(stakeholders finding 1)*

- **Exit code contract:** Define `0` = clean quit (user pressed `q`), non-zero = error
  (crash, port failure). Enables scripting and CI assertions.
  *(stakeholders finding 5)*

- **Accessibility non-goal:** Add one sentence: "Accessibility (screen reader, high-contrast)
  is not addressed in Phase 1." Prevents future confusion.
  *(gaps observation)*

- **Clipboard copy:** The PRD non-goals "no structured file logging" but users will want to
  save a session. Explicitly state whether clipboard copy is out of scope for Phase 1 to prevent
  scope expansion on launch day.
  *(gaps finding 7, scope observation)*

- **`RichLog` performance under bursts:** EnOcean button presses generate repeated telegrams.
  Very high `RichLog.write()` call rates (>100/s) can cause UI stutter. Consider batching
  writes (flush every 50 ms) if burst testing reveals lag.
  *(feasibility finding 3)*

---

## Confidence Assessment

| Dimension               | Score | Notes                                                              |
|-------------------------|-------|--------------------------------------------------------------------|
| Requirements completeness | M   | Happy paths complete; error states and thresholds mostly absent    |
| Technical feasibility     | H   | Stack is well-suited; RSSI and filter scope are the only unknowns  |
| Scope clarity             | M   | Core sniffer tight; base ID, fixture, filter boundaries disputed   |
| Ambiguity level           | M-L | Pause contradiction and filter model need resolution before coding |
| Overall readiness         | M   | Can start display core; 3 binary decisions block integration tests |

---

## Next Steps

- [ ] Answer Q1–Q8 above (see "Before You Build" section)
- [ ] Promote Open Questions 1 (log retention), 6 (RORG format), 7 (log line format) to
      resolved requirements in the PRD
- [ ] Update bead eat-wfs-phb6e or create a follow-up bead with the resolved answers
- [ ] Once Q3 (filter model) is answered, scope the Phase 1 filter ticket accordingly
- [ ] Verify `enocean-async` RSSI exposure before writing the sniffer worker
- [ ] Pour `design` convoy to generate implementation plan after Q1–Q8 are resolved
