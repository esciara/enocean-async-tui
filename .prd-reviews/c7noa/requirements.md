# Requirements Completeness

## Summary

The Phase 1 Sniffer MVP PRD is unusually well-specified for a draft. It names concrete goals, defines
non-goals, includes test scenarios, and anticipates open questions. That said, several acceptance
conditions are defined only at the feature level ("show timestamp, sender ID, RORG, payload, RSSI")
without thresholds that would make them verifiable in a test. A few non-functional requirements
(rendering latency, queue overflow behaviour, accessibility) are absent entirely.

## Findings

### Critical Gaps / Questions

**1. No acceptance threshold for "within 100 ms of the command starting" (Goal 1)**
- The PRD states "see a live, scrolling log…within 100 ms of the command starting" but offers no
  definition of what is being measured, no CI gate, and no fallback if the goal is missed.
- Why this matters: 100 ms is an aggressive target that touches Python startup, serial init, and
  Textual rendering. Without a measurement strategy it cannot be tested and will drift.
- Question: Is 100 ms a hard SLA (CI will fail if missed) or an aspirational target? What is the
  measurement baseline — wall clock from process start, or first telegram received?

**2. Pause buffer overflow behaviour is undefined**
- Goal 4 ("No data lost while paused") and the Rough Approach mention "DongleService queue bound of
  256". What happens at 257? Silent drop? Error displayed? Oldest-out?
- Why this matters: Production-incident scenario — user pauses during a telegram burst. Silently
  dropping is probably fine for a sniffer, but the requirement is currently contradicted ("no data
  lost") by the implementation detail ("queue bound of 256").
- Question: Should "no data lost while paused" be scoped to "within the 256-entry queue" or is a
  larger/unbounded buffer required?

**3. Auto-reconnect requirements are incomplete**
- "Auto-reconnect from Phase 0 continues to work" is a pass-through requirement, not a Phase 1
  requirement. There are no acceptance criteria: how long can reconnection take? Is there a max
  retry count? Is any UI feedback expected during the reconnect window?
- Why this matters: The sniffer view may show stale data or a blank log during reconnect. The user
  has no specification for what to expect.
- Question: What is the UX contract for the reconnect interval? Is a spinner, counter, or "last
  seen N seconds ago" message in scope?

**4. Log retention bound is in Open Questions, not in requirements**
- Open Question 1 proposes 10 000 lines as a candidate. This should be a requirement with a
  default value, configurability contract, and a test.
- Why this matters: Without a bound, unbounded log growth is an implicit acceptance of OOM risk on
  long sessions. The `RichLog` widget will degrade rendering performance long before OOM.
- Question: Define the default retention bound and whether it is user-configurable in Phase 1 or
  Phase 2.

### Important Considerations

**5. Coverage gate stays ≥ 80% — no per-module floors**
- The PRD inherits the 80% project-wide coverage gate but says nothing about new modules needing
  higher coverage. The sniffer worker and filter logic are the core of Phase 1; 80% project-wide
  could mask 30% coverage on the new code if older code carries the average.
- Suggestion: add a per-module gate (e.g., `src/enocean_async_tui/ui/workers/` ≥ 90%).

**6. Filter entry UX only specified for single-ID case; error handling absent**
- The PRD says user types 8 hex digits. What happens if they type 7, or non-hex characters?
  Is the filter accepted immediately (live filter as they type) or on Enter?
- Suggestion: specify input validation and error feedback before implementation.

**7. FakeDongle replay path in sniffer (Goal 6) depends on a fixture that doesn't exist yet**
- The PRD describes "replaying a recorded session fixture" but no such fixture is specified.
  Which fixture file? How is it selected? Who creates it?
- Suggestion: define the fixture format and location as part of Phase 1 scope.

### Observations

- Goal 7 references "decoder unit (n/a for Phase 1, no decoding)" which is correct but
  slightly confusing — the test layer exists even though the decoder doesn't. This will
  cause friction during onboarding.
- The Pilot test strategy is named but the framework version and import path are not
  specified. Confirm `textual.testing.Pilot` is the intended class.
- Goal 8 ("CI gate stays green") is a meta-requirement, not a feature requirement. It belongs in
  CONTRIBUTING.md, not the feature PRD.

## Confidence Assessment

**Medium.** The requirements cover the happy paths well and non-goals are clearly stated.
The main gaps are around testability thresholds, queue boundary conditions, and the log retention
policy. None are blockers to starting implementation, but the pause/drop ambiguity and the 100 ms
target need clarification before the first integration test is written.
