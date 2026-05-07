# Scope Analysis

## Summary

The Phase 1 Sniffer MVP PRD has a well-structured Non-Goals section that covers the most obvious deferral candidates (decoding, device registry, teach-in, MQTT). The core sniffer loop — receive telegrams, display them, pause, clear — is tightly scoped and deliverable. The scope risk is concentrated in three areas: (1) the filter feature, where Scenario A implies retroactive re-render but the Rough Approach implies prospective-only — a 3× scope difference that is unresolved; (2) base ID retrieval, which Goal 3 requires but Open Question 2 defers — a direct contradiction; and (3) several implicit scope items (RORG-to-name table, FakeDongle fixture format, log retention limit) that are treated as implementation details but belong in requirements.

The display core can be implemented immediately. Two binary decisions — filter model (retroactive vs. prospective) and base ID in Phase 1 (yes/no) — must be resolved before those features are coded. The filter in particular is the single highest scope-expansion risk: if the stakeholder interprets Scenario A literally, Phase 1 becomes significantly larger.

---

## Findings

### Critical Gaps / Questions

**1. Filter retroactivity: Scenario A contradicts the Rough Approach (3× scope risk)**
- Scenario A says Alice "presses `f`, enters `ABCD1234`, and the log now shows only that device." The phrase "log now shows only" implies existing entries are re-filtered — retroactive.
- The Rough Approach says the filter is "held as `filter_id: int | None`" and "`TelegramReceived` handler skips non-matching entries when filter is active" — prospective only.
- Retroactive filtering requires a parallel in-memory buffer of every received telegram, a full `RichLog.clear()` + repopulate on filter change, and significantly more test coverage.
- Prospective-only filtering is ~10 lines of code; retroactive is a new data model.
- **Suggested clarifying question:** "Does applying a filter re-render the existing log, or does it only gate new incoming telegrams? Rewrite Scenario A to match the intended behavior."

**2. Base ID retrieval: Goal 3 requires it; Open Question 2 defers it**
- Goal 3 explicitly lists "dongle base ID" as a header field to display.
- Open Question 2 asks whether to issue `COMMON_COMMAND_RBASE` in Phase 1 or Phase 2.
- Retrieving the base ID requires sending an outgoing command and parsing the response — a new protocol capability not otherwise needed in Phase 1 (sniffer is receive-only per the non-goals).
- If deferred, Goal 3 must be updated to "header shows `–` for base ID in Phase 1."
- **Suggested clarifying question:** "Is base ID retrieval in Phase 1 scope? If yes, spec the async request/response flow. If no, update Goal 3 to remove base ID from the Phase 1 header."

**3. Pause queue bound: Goal 4 ("no data lost") contradicts the 256-entry cap in Rough Approach**
- Goal 4 states "telegrams queue while paused, no data lost."
- Rough Approach says "buffers telegrams in a local `deque` while paused" with DongleService's 256-entry queue bound cited as the safety net.
- An unqualified "no data lost" guarantee with a bounded queue is contradictory. Engineers will implement this differently.
- **Suggested clarifying question:** "Is 'no data lost' an absolute guarantee (unbounded deque, memory risk) or scoped to 'no data lost within 256-entry bursts' with silent drops beyond that? Add an explicit overflow behavior to Goal 4."

**4. FakeDongle fixture for demo path is undefined scope**
- Goal 6 and Scenario C require "a recorded session fixture" enabling demo without hardware.
- No fixture format is defined anywhere in the PRD (binary ESP3 capture? Python list of `RawTelegram`-compatible dicts?).
- Creating a fixture file and defining its format is Phase 1 scope work not acknowledged in Requirements.
- **Suggested clarifying question:** "What is the expected format for the recorded session fixture, and is authoring that fixture file an explicit Phase 1 deliverable?"

**5. RORG-to-name table is implicit in-scope work not acknowledged in Requirements**
- The log line format requires displaying `RPS (0xF6)` — a symbolic name mapped from an RORG byte.
- The non-goals exclude "no device registry," but a 5-entry lookup table (`0xF6 → RPS`, `0xD5 → 1BS`, `0xA5 → 4BS`, etc.) is a different kind of scope than a device registry.
- Unknown RORG bytes (Smart ACK, MSC, SYS-EX) need a defined fallback.
- This is small (~20 lines) but should be listed in Requirements to avoid "it wasn't in scope" confusion.
- **Suggested clarifying question:** "Add an explicit requirement: 'Phase 1 includes an RORG-byte-to-name lookup table covering the standard EnOcean types; unknown RORG bytes are displayed as `UNK (0xXX)`'."

---

### Important Considerations

*(Can start implementation on display core; these need resolution before the relevant feature is coded.)*

**1. "100 ms of the command starting" goal is not achievable and will become a scope negotiation**
- Python 3.14 + uv startup + Textual compose + serial port init typically takes 500–1500 ms.
- This number will generate a bug report on first demo. Either remove the numeric target or redefine it as "within 100 ms of the dongle being ready to emit," testable with FakeDongle.
- Leaving it as written sets a gate that CI will never enforce and users will dispute.

**2. `q` key scope when filter Input has focus**
- Textual widget focus changes key binding priority: when the filter `Input` is focused, `q` is consumed as text input, not as a quit command.
- Undefined behavior will produce a user-facing bug on first demo ("I can't quit after typing in the filter").
- Define: `q` always quits regardless of focused widget (requires app-level binding with `priority=True`), OR: `Escape` is required to exit filter before `q` works.

**3. Log retention is an Open Question that must become a Requirement**
- Open Question 1 asks about `RichLog` max lines. This cannot remain open through implementation.
- An unbounded `RichLog` on a long-running session (hours, continuous EnOcean traffic) is a real memory/render issue.
- `RichLog(max_lines=10_000)` should be promoted to a Requirement with an explicit note that it is the configurable default.

**4. `threading.Event` in Rough Approach is a latent bug**
- The Rough Approach says "worker checks a `threading.Event` (or asyncio-compatible flag)."
- In a single-loop asyncio context, `threading.Event.wait()` blocks the event loop.
- This needs to be `asyncio.Event` — not a refactor, but a correctness requirement to state explicitly in the Rough Approach.

**5. RSSI availability is an external dependency risk**
- The log line format includes RSSI in dBm, but `enocean-async` RSSI availability depends on the ESP3 optional data section being present and exposed.
- If RSSI is absent for some telegram types (or not exposed in the library model), the log format breaks.
- Verify before writing the sniffer worker; define the fallback display (`–` or `N/A`) if absent.

**6. Phase 0 API completeness: `DongleService.telegrams()` must exist**
- The constraint "Phase 0 foundation is fixed, additions only" presupposes that `DongleService` already exposes a `telegrams()` async iterator.
- If this API doesn't exist in Phase 0, Phase 1 must add it — which is a Phase 0 scope gap, not a Phase 1 scope gap, but it will appear as Phase 1 work.
- Verify the Phase 0 API before starting Phase 1 implementation.

---

### Observations

**1. Filter is the highest schedule risk — natural Phase 1.5 seam**
- The display core (sniffer worker + RichLog + pause + clear) delivers Scenarios A, B, D with no filter.
- Scenario A can be partially satisfied by prospective-only filter (new telegrams after `f` is pressed).
- If the filter is deferred to Phase 1.5, Phase 1 ships faster and avoids the retroactivity decision entirely.
- Recommend marking filter as "Phase 1 stretch goal, Phase 1.5 if retroactive" to give implementation flexibility.

**2. Base ID is a Phase 2 capability drifting into Phase 1**
- Base ID retrieval requires sending a command telegram (`COMMON_COMMAND_RBASE`) — the first outgoing command in the codebase.
- All of Phase 1 is read-only (non-goal: "no outgoing commands"). Base ID retrieval breaks this.
- The benefit is a header field display; the cost is a new protocol capability category.
- Recommend deferring to Phase 2 and updating Goal 3 to show `–`.

**3. Clipboard copy / session export is the #1 post-launch stakeholder request**
- Scenario B ("copies the IDs to a spreadsheet") implies manual terminal copy-paste.
- The Non-Goals exclude "no structured file logging" but do not exclude clipboard copy.
- This gap will produce a Day 1 feature request. Add to Non-Goals: "No clipboard copy or session export in Phase 1."

**4. Platform serial port naming needs explicit treatment for the "60 seconds" goal**
- The PRD uses `/dev/ttyUSB0` (Linux). macOS: `/dev/cu.usbserial-*`. Windows: `COM3`.
- The "demo-able in 60 seconds" goal requires knowing the correct port.
- Explicitly state: `--port` is required with no default, and document the platform-specific values in the README as part of Phase 1 scope.

**5. `clear` + paused state interaction is undefined**
- If the user presses `c` while paused, the visible log clears but the pause buffer still holds queued telegrams.
- On resume, the "cleared" log immediately fills again — surprising behavior.
- Define: `c` clears both the visible log AND the pause buffer (clean slate), or clears only the visible log (no data loss).

**6. Coverage gate scope: 80% project-wide may mask new sniffer code quality**
- The 80% gate applied project-wide could pass even if the new sniffer worker module has 40% coverage, offset by well-tested Phase 0 code.
- Recommend adding a per-module floor for `src/enocean_async_tui/ui/workers/` (≥ 90%) to match the TDD-non-negotiable constraint.

---

## Confidence Assessment

The scope is **Medium** confidence overall. The Non-Goals section is unusually thorough for a draft, and the core display path is well-defined. The gaps are concentrated:

- **High confidence:** Display core (sniffer worker, RichLog, pause, clear) — can be implemented immediately.
- **Low confidence:** Filter feature — retroactivity ambiguity makes this a 1× or 3× scope item depending on interpretation; highest risk.
- **Low-Medium confidence:** Base ID and fixture — both have direct contradictions between Goals and Open Questions that must be resolved before coding.
- **Medium confidence:** RORG table, log retention, `asyncio.Event` — small and decidable, but need to move from Rough Approach to Requirements.

**Overall readiness: Medium.** Phase 1 can start on the display core. The filter retroactivity question (Critical Gap 1) and base ID decision (Critical Gap 2) must be resolved before those features are scoped into the sprint.
