# Requirements Completeness

## Summary

The Phase 1 Sniffer MVP PRD is better than average: goals are concrete, non-goals are
explicit, and four user scenarios ground the abstract requirements in real behavior.
However, several acceptance conditions are left open (log line format, RORG display,
pause UX, RSSI format) — these are listed as "Open Questions" but have not been
resolved. Until they are, tests cannot be written for those features without guessing.
Additionally, Phase 0.5 (frame capture tool) is referenced in the review brief but
absent from the PRD entirely, leaving a gap between Phase 0 and Phase 1 with no
written specification.

## Findings

### Critical Gaps / Questions

**1. Phase 0.5 is mentioned in the review assignment but not in the PRD**
- The review brief states: "Phase 0.5 (frame capture tool connecting to real dongle)".
  The PRD skips from Phase 0 directly to Phase 1, with no mention of a Phase 0.5
  stepping stone.
- Why this matters: if Phase 0.5 is a prerequisite for Phase 1 (e.g., validating
  real dongle connectivity before building the full TUI), its absence means the
  Phase 1 PRD's assumptions about what "Phase 0 foundation is fixed" covers may be
  incorrect. A builder won't know whether to implement it first or skip it.
- Suggested clarifying question: Is Phase 0.5 a discrete deliverable that must ship
  before Phase 1 begins? If so, it needs its own spec. If it is already complete or
  subsumed into Phase 1, remove the reference to avoid confusion.

**2. Five "Open Questions" in the PRD are unresolved requirements, not open questions**
- Open Questions 1–7 cover: log retention (OQ1), base ID retrieval (OQ2), RSSI
  format (OQ3), pause UX (OQ4), filter mode (OQ5), RORG name vs hex (OQ6), log line
  format (OQ7).
- Of these, OQ1 (retention), OQ4 (pause UX), OQ6 (RORG display), and OQ7 (log line
  format) are acceptance conditions, not design choices. A test for "the log line
  shows RORG correctly" cannot be written until the format is decided.
- Why this matters: at least 3 of the 5 stated integration tests (telegram display,
  filter, pause) depend on knowing the exact log line format. Implementing first and
  speccing later produces tests that assert whatever the code happened to do, not
  what was required.
- Suggested clarifying question: Before implementation begins, can the author
  resolve OQ4 (pause banner), OQ6 (RORG format), and OQ7 (log line column order and
  payload truncation) as requirements?

**3. "Within 100 ms" startup latency goal has no measurement definition or test gate**
- Goal 1 says "see a live, scrolling log…within 100 ms of the command starting."
  There is no specification of the measurement baseline (wall clock? time-to-first
  telegram? time-to-first-rendered-line?), no CI enforcement, and no fallback if
  the target is missed in practice.
- Why this matters: Python startup + serial port initialization + Textual's first
  render cycle routinely exceed 100 ms in isolation. Without a measurement protocol
  this goal is untestable and will be silently violated or silently exempted.
- Suggested clarifying question: Is 100 ms a hard gate (CI will fail if missed) or
  an engineering aspiration? What exactly is being clocked?

**4. "No data lost while paused" contradicts the 256-entry queue bound**
- Goal 4 states "telegrams queue while paused, no data lost." The Rough Approach
  section mentions "DongleService queue bound of 256." These two statements
  contradict each other: if a burst exceeds 256 telegrams while paused, data loss
  is certain.
- Why this matters: a QA engineer writing the pause test cannot assert "no data
  lost" without knowing the actual guarantee. The real requirement is probably
  "no data lost within the queue bound" — but that should be stated explicitly,
  along with the overflow policy (drop oldest? drop newest? alert user?).
- Suggested clarifying question: Should Goal 4 read "no data lost up to queue
  capacity of N telegrams"? What happens when the queue is full?

**5. FakeDongle replay fixture required by Goal 6 is not specified**
- Goal 6 says "pressing a recorded switch replays correctly in the sniffer view,
  enabling demos without hardware." The Rough Approach says the integration test
  uses "a recorded session fixture." No such fixture is defined: filename, format,
  location, and who creates it are all unspecified.
- Why this matters: without a defined fixture, Goal 6 is not implementable, and
  the Scenario C user story cannot be validated by any test.
- Suggested clarifying question: What is the file format, filename, and location of
  the recorded session fixture? Is creating it part of Phase 1 scope?

### Important Considerations

**6. Filter entry validation is not specified**
- The PRD says the user "types 8 hex digits" to filter by sender ID, and "cleared
  with `f` again or `Escape`." It does not specify: what happens on invalid input
  (non-hex, fewer/more than 8 characters)? Is the filter applied live (per
  keystroke) or on Enter? Is the current filter displayed anywhere in the UI?
- This will drive the Input widget's validator and the filter-mode integration test.

**7. Auto-reconnect acceptance criteria are inherited, not defined**
- Goal 5 ("Auto-reconnect from Phase 0 continues to work") defers to Phase 0 without
  stating the Phase 0 criteria. If Phase 0's acceptance criteria are clear and
  tested, this is acceptable. If not, Phase 1 inherits an untestable goal.
- This is only a blocker if Phase 0 auto-reconnect tests don't already exist.

**8. Rendering performance under load is not specified**
- The PRD does not define a telegram rate above which rendering quality can degrade,
  nor a maximum frame time for the TUI under load. In a dense EnOcean environment
  (many sensors, short intervals), the `RichLog` may fall behind.
- Suggested: add a non-functional note: "at up to N telegrams/second, log appends
  must complete without perceptible UI lag." A reasonable Phase 1 N is 10–20.

**9. Coverage gate is project-wide; new modules could be under-covered**
- Goal 8 says "coverage gate stays ≥ 80%." The sniffer worker and filter logic are
  the sole new code in Phase 1. A project-wide 80% gate could be satisfied while
  the new files have 40% coverage, carried by Phase 0's tested modules.

### Observations

- The Rough Approach section is detailed enough to inform implementation, but it
  is located inside the PRD rather than a separate design doc. This means the PRD
  conflates requirements (what to build) with design (how to build it). Future
  reviews of the design can't be done independently.
- The non-goals list is one of the stronger parts of this PRD. It is specific and
  directly addresses scope creep risks (no decoding, no registry, no logging).
- Goal 7 notes "decoder unit (n/a for Phase 1)" — this is correct but the presence
  of a test layer with no tests in it may cause confusion during CI setup. A note
  in the test plan would clarify.
- "TDD is non-negotiable" is stated as a constraint, but there is no TDD workflow
  guidance (red-green-refactor, test file locations, test naming conventions).
  New contributors will need to infer this from existing Phase 0 tests.

## Confidence Assessment

**Medium.** The PRD covers the happy path thoroughly and non-goals are clearly
drawn. The main gaps are: five unresolved open questions that are actually
acceptance conditions (OQ1, OQ4, OQ6, OQ7 in particular), the missing Phase 0.5
spec, and the contradictory pause-buffer requirement. None of these should block
starting work on the unambiguous goals (scrolling log, header, key bindings), but
the integration tests for display formatting and pause behavior cannot be finalized
until OQ4, OQ6, and OQ7 are resolved.
