# PRD Review: Phase 1 — Sniffer MVP (live EnOcean telegram log)

## Executive Summary

The PRD is in good shape for a draft: non-goals are explicit, user scenarios are
concrete, and TDD/mypy constraints show engineering discipline. Eight critical
questions raised by the first review cycle have been answered by the human author
(Q1–Q8 in the PRD). Those answers resolve the pause semantics contradiction,
filter retroactivity model, log line format, and base ID deferral. Three
significant gaps remain after those answers: Phase 0.5 has zero specification
(all six review legs flagged this independently), the FakeDongle replay fixture
required by Scenario C is still unspecified, and Q6 introduced new scope
(auto-discovery of dongles) without acceptance criteria. The core sniffer loop
is ready to implement; those three gaps must be closed before Phase 1 can be
fully scoped. Overall readiness: **Medium-High**.

---

## Before You Build: Critical Questions

*(Must be answered before implementation starts)*

### Phase 0.5 Scope

**Q1: What exactly is the Phase 0.5 frame capture tool, and is it a prerequisite for Phase 1?**
- Why this matters: Phase 0.5 is named in the feature description
  ("Spec and implement Phase 0.5 (frame capture tool) and Phase 1 (Sniffer MVP)")
  but is completely absent from the PRD. All six review legs flagged this
  independently — it is the highest-confidence gap in this review. If Phase 0.5
  produces the JSONL recording fixture that FakeDongle needs for Scenario C, then
  Phase 1's demo path is blocked until Phase 0.5 ships. Neither the deliverables,
  format, acceptance criteria, nor the relationship to Phase 1 are written
  anywhere.
- Found by: stakeholders (finding 2), ambiguity (finding 6), requirements
  (finding 1), gaps/missing (finding 1), scope (finding 4), feasibility
  (finding 1) — **flagged by all six legs**
- Suggested answer options:
  a. Phase 0.5 is a separate deliverable with its own PRD/bead; it precedes
     Phase 1 and is responsible for producing `tests/fixtures/recording.jsonl`
  b. Phase 0.5 is in scope for this PRD and needs a "Phase 0.5" section added
  c. Phase 0.5 is already complete (if so, link to it and confirm fixture format)
  d. Phase 0.5 is deferred; Phase 1 ships a hand-crafted fixture and
     Scenario C is the capture use case for a future phase

---

**Q2: Where does the FakeDongle replay fixture live, what is its exact format, and what happens when replay exhausts?**
- Why this matters: Q6 in the PRD answers "offer FakeDongle fallback" on port
  failure, and Goal 6 requires "pressing a recorded switch replays correctly in
  the sniffer view." Scenario C depends on a bundled fixture. The Phase 0
  `FakeDongle` implementation uses JSONL with `telegram_hex`, `rssi_dbm`,
  `t_offset_ms` fields — but this format is not documented in the PRD, no fixture
  file exists in the repo, and end-of-replay behavior is unspecified (the UI
  goes silent with no indication when replay ends).
- Found by: requirements (finding 5), gaps/missing (findings 3 and 4), scope
  (finding 4), feasibility (finding 6)
- Sub-decisions needed:
  - **Location:** `src/enocean_async_tui/fixtures/`, `tests/fixtures/`, or
    bundled as package data in `pyproject.toml`?
  - **Format:** Confirm JSONL with `telegram_hex` / `rssi_dbm` / `t_offset_ms`
    is the canonical format and document it
  - **End-of-replay:** Loop continuously, freeze with "End of recording" message,
    or transition back to a reconnecting state?
  - **Creating the fixture:** Is authoring the fixture file an explicit Phase 1
    deliverable, or does Phase 0.5 produce it?

---

### New Scope from Q6 (Auto-Discovery)

**Q3: What are the acceptance criteria for dongle auto-discovery introduced in Q6?**
- Why this matters: The human clarification for Q6 added: "Phase 1 should include
  auto-discovery of connected dongles — when no `--port` is specified (or the
  given port is not found), the app scans for available EnOcean dongles and either
  connects automatically or presents options." This is new scope not in the
  original PRD. There are no requirements, no test strategy, no error cases, and
  no cross-platform specification for this feature. On macOS, dongle discovery
  requires scanning `/dev/cu.usbserial-*`; on Linux, `/dev/ttyUSB*`; on Windows,
  enumerating COM ports.
- Found by: implicit from Q6 human answer; substantiated by gaps/missing
  (finding 10) and stakeholders (finding 2)
- Suggested answer options:
  a. Specify auto-discovery fully (detection method per OS, user prompt when
     multiple dongles found, error when none found) as a Phase 1 requirement
  b. Narrow to: "if exactly one EnOcean-compatible port found, connect to it
     silently; otherwise require `--port`" — minimal discovery, limited scope
  c. Move auto-discovery to Phase 2; Q6 answer reverts to "error modal +
     FakeDongle fallback offer only"

---

### RichLog Test Strategy

**Q4: What is the agreed test strategy for asserting `RichLog` content in Pilot tests?**
- Why this matters: TDD is non-negotiable (PRD constraint), and the primary
  acceptance tests require asserting log line content ("assert all 3 telegrams
  appear in the `RichLog`"). However, Textual's `RichLog` stores rendered Rich
  markup, not raw strings — there is no documented public API for reading back
  lines as plain text. Q3's answer (retroactive filtering) requires a parallel
  in-memory buffer of all received telegrams, which also creates a testable data
  structure that could be the assertion surface. Without a decided strategy, TDD
  cannot start.
- Found by: feasibility (finding 3), stakeholders (finding 6)
- Suggested answer options:
  a. Use `app._telegram_buffer` (the in-memory buffer required by Q3) as the
     assertion surface for content tests; Pilot tests check the buffer, not
     the rendered `RichLog`
  b. Subclass `RichLog` as `TestableRichLog` that shadows writes into a
     `lines: list[str]`; inject it in tests
  c. Use Textual snapshot testing (screenshot comparison) — acceptable for
     regression but not for content assertions in TDD

---

## Important But Non-Blocking

*(Implementation can start on display core; resolve these before the relevant feature is coded)*

- **`asyncio.Event`, not `threading.Event`.** The Rough Approach mentions
  "threading.Event (or asyncio-compatible flag)." In an all-asyncio context,
  `threading.Event.wait()` blocks the event loop thread. Use `asyncio.Event`.
  This is a correctness requirement, not a style preference.
  *(ambiguity finding 2, scope finding 4)*

- **RSSI `None` display.** The log format (from Q5) shows `RSSI -62 dBm`, but
  `RawTelegram.rssi_dbm` returns `None` when the ESP3 optional data section is
  absent (returns `0xFF` for unknown). Define: display as `RSSI –` or `RSSI n/a`.
  *(gaps finding 8)*

- **Timestamp timezone.** Q5 specifies ISO 8601 format
  (`2026-05-07T14:23:01.042`) but does not specify UTC or local time.
  `DongleService` stamps telegrams in UTC; displaying UTC is consistent and avoids
  DST edge cases. Confirm before writing the formatter.
  *(gaps finding 6)*

- **End-of-replay behavior.** When `FakeDongle._replay_loop` exhausts the
  recording, the dongle stays `CONNECTED` but emits nothing. The UI freezes
  silently. Define: loop continuously, or show "End of recording" indicator.
  Needed before Scenario C integration test can pass.
  *(gaps finding 4)*

- **Auto-scroll behavior.** The PRD doesn't specify whether the log auto-scrolls
  on new content when the user has scrolled up. Auto-scroll fighting a user's
  scroll is one of the most common TUI annoyances. Recommend: auto-scroll to
  bottom only when already at bottom; pause auto-scroll when user scrolls up;
  `End` key resumes.
  *(gaps finding 5)*

- **Filter input edge cases.** Q4 says "apply on Enter, show pending state while
  typing." Q5 says the filter "accepts `0x` prefix (strips it for matching)."
  Still unspecified: partial input (fewer than 8 hex chars), invalid characters
  mid-entry, case sensitivity (`abcd1234` vs `ABCD1234`). Define before writing
  the Input validator.
  *(ambiguity findings 5 and 10, gaps finding 7)*

- **`q` key when filter Input has focus.** Textual changes binding priority when
  a widget has focus. `q` typed into the filter will be consumed as text, not
  as quit — unless the binding is declared `priority=True` at app level. Define:
  `q` always quits regardless of focus (requires `priority=True`), OR the user
  must press `Escape` first.
  *(ambiguity finding 17, scope finding 2)*

- **RORG-to-name table scope.** Q5 confirms `RPS (0xF6)` format. Building the
  table is now an acknowledged deliverable. Add to requirements: "Phase 1 ships
  an RORG-to-name lookup for standard EnOcean types; unknown RORG bytes display
  as `UNK (0xXX)`."
  *(scope finding 5, feasibility finding 7)*

- **`enocean-async` upstream ownership.** No named owner of the library
  relationship. If Phase 1 discovers a bug (e.g., RSSI absent for certain frame
  types), who files the upstream issue and what is the fallback?
  *(stakeholders finding 5)*

---

## Observations and Suggestions

- **Retroactive filter + in-memory buffer is Phase 1's largest new scope item.**
  Q3 decided retroactive filtering. This requires buffering all received telegrams
  (up to 10,000 per the log retention limit from Q1). At 50–200 telegrams/min
  (dense environment), that's 50–200 minutes of history in memory. This is
  correct and consistent, but it must be acknowledged as a deliberate trade-off
  in the design — not just a detail of the filter implementation.

- **Auto-discovery (from Q6) may be the single biggest schedule risk.** Cross-platform
  serial port discovery is non-trivial: it requires either `pyserial`'s
  `serial.tools.list_ports` (and a way to identify EnOcean vs non-EnOcean ports),
  a hardcoded pattern match per OS, or `udev` rules on Linux. This was not in the
  original scope and has no test strategy. If timeline is constrained, narrow to
  option (b) in Q3 above or defer to Phase 2 entirely.

- **Phase 0.5 / fixture dependency is the critical path blocker.** Scenario C
  cannot pass until a bundled fixture exists. If Phase 0.5 is a separate polecat
  assignment, Phase 1 must not begin Scenario C implementation until Phase 0.5
  has shipped a fixture. The integration test scaffold should be stubbed with a
  `pytest.skip("fixture not yet available")` guard until then.

- **Building-occupant privacy.** EnOcean telegrams can encode motion, occupancy,
  and access-control events. The PRD has no mention of disclosure or consent
  mechanisms. For an open-source CLI tool this is low legal risk, but if the tool
  is later adopted in EU commercial contexts, the absence of any acknowledgment
  will surface. Add one sentence to Non-Goals: "Privacy compliance for commercial
  building deployments is out of scope for Phase 1."
  *(stakeholders finding 1)*

- **Per-module coverage floor.** 80% project-wide may mask low coverage on new
  sniffer code if Phase 0 modules carry the average. Recommend adding a per-path
  floor: `src/enocean_async_tui/ui/workers/` ≥ 90%.
  *(requirements finding 9, scope finding 6)*

- **Clipboard copy is an implied Day 1 feature request.** Scenario B ends with
  "copies the IDs to a spreadsheet." The Non-Goals exclude file logging but not
  clipboard copy. Add explicitly: "No clipboard copy or session export in Phase 1."
  *(scope observation 3)*

- **Concurrent instance protection.** Two `enocean-tui` instances targeting the
  same serial port will race. This is an observation, not a blocker — serial ports
  are exclusive, so the second instance will fail to open — but the error message
  should be friendly ("Port already in use by another process").
  *(gaps observation)*

---

## Confidence Assessment

| Dimension                  | Score | Notes                                                                                             |
|----------------------------|-------|---------------------------------------------------------------------------------------------------|
| Requirements completeness  | M-H   | Core goals complete; Phase 0.5 and auto-discovery introduced gaps                                |
| Technical feasibility      | H     | Stack proven; RichLog test strategy is the primary engineering uncertainty                        |
| Scope clarity              | M     | Display core + pause + clear: tight. Filter (retroactive, buffer), fixture, auto-discovery: open |
| Ambiguity level            | M-L   | Q1–Q8 resolved main contradictions; 4 critical questions remain                                  |
| Overall readiness          | M-H   | Can build sniffer core + pause + clear immediately; Q1–Q4 above block fixture and full scoping   |

---

## Next Steps

- [ ] Answer Q1–Q4 above (Phase 0.5, fixture spec, auto-discovery scope, RichLog test strategy)
- [ ] Resolve non-blocking items before coding their respective features:
      asyncio.Event, RSSI None, timestamp timezone, end-of-replay, auto-scroll,
      filter edge cases, `q` focus priority
- [ ] Add auto-discovery acceptance criteria to PRD if it stays in Phase 1 scope (from Q6 answer)
- [ ] Add privacy non-goal sentence: "Privacy compliance for commercial building
      deployments is out of scope for Phase 1"
- [ ] Add clipboard copy to Non-Goals
- [ ] File separate bead for Phase 0.5 if it is a distinct deliverable
- [ ] Pour `design` convoy to generate implementation plan after Q1–Q4 are resolved
