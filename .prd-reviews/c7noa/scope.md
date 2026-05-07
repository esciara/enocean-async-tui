# Scope Analysis

## Summary

The PRD's non-goals section is one of its strongest elements — it clearly defers decoding, device
registry, teach-in, outgoing commands, and file logging to later phases. However, several
requirements in the Goals section are Phase 2 features in disguise (particularly base ID retrieval
and the filter UX), and the "FakeDongle replay" goal creates an implicit dependency on a fixture
system that is not in scope. The boundary between Phase 1 and Phase 2 is blurry in three places.

## Findings

### Critical Gaps / Questions

**1. Base ID retrieval is Phase 2 scope in Phase 1 clothing**
- Goal 3: "Header displays: dongle base ID"
- Rough Approach: "base ID (from dongle or `–` until resolved)"
- Open Question 2: "Should Phase 1 issue the base-ID request on connect, or defer to Phase 2?"
- This is a mini-feature: it requires a `COMMON_COMMAND_RBASE` outgoing command, response
  parsing, and async state management. It was explicitly deferred to Open Questions, meaning
  the scope boundary is actively in dispute.
- Why this matters: If base ID retrieval is in scope, it expands the dongle command interface.
  If it's deferred, Goal 3 is partially unimplementable and the header shows `–` always.
- Question: Decide now: is base ID retrieval in or out of Phase 1 scope? This is a binary
  decision with concrete implementation consequences.

**2. FakeDongle replay path (Goal 6) requires a fixture that is out of scope**
- Goal 6 says: "pressing a recorded switch replays correctly in the sniffer view, enabling
  demos without hardware"
- This requires a recorded session fixture (binary or JSON file of telegram sequences). The
  PRD does not specify: where the fixture lives, what format it uses, how it is selected,
  or who records it.
- Why this matters: The fixture is a deliverable prerequisite for Goal 6. Without it, Scenario C
  (demo without hardware) cannot be tested. This is implicitly Phase 1 scope but never stated.
- Question: Is the replay fixture creation in Phase 1 scope? What format and location?

**3. Filter mode as a Phase 1 feature is scope-creep risk**
- Goal 4 includes "`f` — enter filter mode (show only a given sender ID)"
- Open Question 5 explicitly asks about single vs. multi-ID filtering
- The PRD defers multi-filter to "Phase 1 scope: single ID" — but even single-ID filter with
  a full inline Input widget and Escape-to-clear is a non-trivial UI component.
- For an MVP sniffer, filter is a convenience feature. The core value (see raw traffic) is
  achievable without it.
- Question: Is the filter binding strictly required for Phase 1 demo-able value, or could it
  be deferred to Phase 1.1? If required: define the minimum scope (prospective-only, single ID,
  no retroactive re-render).

### Important Considerations

**4. "Pause queues while paused, no data lost" expands scope if retroactive filter is added**
- If filter is retroactive (re-renders existing log), the pause buffer design must also be
  retroactive-filter-aware. These two features interact significantly.
- Suggestion: Implement pause before filter. Define filter as prospective-only in Phase 1.

**5. RORG name mapping is a soft registry**
- Displaying "RPS (0xF6)" requires a mapping table of RORG codes to names. The PRD non-goals
  "no device registry" but a RORG-name table is a mini-registry.
- It is small (< 15 entries in the EnOcean spec), but it's scope that hasn't been explicitly
  acknowledged.
- Suggestion: State explicitly "RORG-to-name table included in Phase 1 scope" in non-goals or
  requirements.

**6. `c` key (clear log) interaction with pause**
- What happens if the user presses `c` while paused? The visible log clears but the pause
  buffer still has queued telegrams. When resumed, the cleared log will suddenly fill with
  buffered items — possibly confusing.
- This edge case is not addressed in the PRD.
- Suggestion: Define: `c` while paused clears both the display buffer AND the pause buffer,
  OR only the display buffer.

### Observations

- The MVP is well-defined and could be shipped without filter (`q`, `c`, `p` only) and still
  deliver the core value of Scenario A and B. The filter is the one feature most likely to
  slip schedule.
- "No multi-dongle support" is correctly non-goaled. If this were in scope, the Phase 0
  architecture (single DongleService instance) would need rethinking.
- "No structured file logging" as a non-goal is correct but users will want clipboard copy
  almost immediately. Consider a pre-emptive non-goal statement: "no clipboard export in
  Phase 1" to prevent scope expansion on launch day.
- Phase 4 (file logging) and Phase 2 (teach-in) are referenced by number but no Phase 2/3/4
  PRDs exist yet. Engineers cannot evaluate whether their Phase 1 implementation will
  support those phases. A one-paragraph "future-phase constraints" note would help.

## Confidence Assessment

**Medium.** The core sniffer (display, pause, clear) is tightly scoped. The three disputed
areas (base ID, FakeDongle fixture, filter) need binary decisions before sprint planning.
None of them should expand scope significantly if decided conservatively (base ID deferred,
fixture defined as a small committed file, filter prospective-only).
