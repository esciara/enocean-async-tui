# Ambiguity Analysis

## Summary

The PRD is written with unusually precise language for a draft, but several constructs are
ambiguous enough to cause implementation divergence. The most significant ambiguities cluster
around "pause" semantics (what exactly is preserved), the filter interaction model (live vs.
committed), and the RORG display format (the "proposal" in Open Questions is not a decision).
Two requirements appear to contradict each other on the topic of data loss during pause.

## Findings

### Critical Gaps / Questions

**1. "No data lost" vs. "queue bound of 256" — direct contradiction**
- Goal 4: "telegrams queue while paused, no data lost"
- Rough Approach: "buffers telegrams in a local deque while paused; flushes on resume"
  (with the 256-bound mentioned in Scenario D)
- These two statements are incompatible: either data can be lost (when queue is full) or the
  queue must be unbounded.
- Why this matters: Two engineers will implement this differently. One will silently drop at 256;
  the other will grow the deque indefinitely.
- Question: Is "no data lost" an absolute guarantee or "no data lost within a reasonable burst"?
  Define the queue bound and the on-overflow policy (drop-oldest, drop-newest, block sender?).

**2. Filter mode: "enter filter mode" — live or committed?**
- Goal 4: "`f` — enter filter mode (show only a given sender ID)"
- Rough Approach: "filter entry widget…typed as 8 hex digits, cleared with `f` again or `Escape`"
- Open Question 5: "Single sender ID at a time…Multi-filter is more powerful"
- Ambiguity: Does the filter apply character-by-character as the user types (live filter,
  showing partial matches), or only after the user presses Enter? Does the existing log get
  retroactively filtered, or only new telegrams?
- Why this matters: Retroactive filtering (re-render existing log) vs. prospective filtering
  (only new telegrams) are fundamentally different UX models.
- Question: Is the filter (a) prospective-only or (b) retroactive? Does it apply on Enter
  or on each keystroke?

**3. RORG display format is not decided — Open Questions 6**
- The PRD presents "name + hex in parentheses: `RPS (0xF6)`" as a "proposal". This is an Open
  Question, not a resolved requirement. Goal 2 says "RORG name" without specifying format.
- Why this matters: Without a decided format, every engineer will implement a different log
  line layout, breaking the "works with FakeDongle replay path" test.
- Question: Resolve: is RORG shown as name only, hex only, or "name (hex)"?

**4. Log line format is in Open Questions, not in requirements**
- Goal 2: "timestamp, 32-bit sender ID (hex), RORG name, raw payload hex, and RSSI in dBm"
- Open Question 7 proposes: `14:23:01.042  0xABCD1234  RPS (0xF6)  70  RSSI -62 dBm`
- The "proposal" leaves column order, separator character, payload truncation, and timestamp
  precision unresolved.
- Why this matters: The format is part of the acceptance test — if Pilot looks for a specific
  string in the `RichLog`, it needs a fixed format.
- Question: Decide the exact log line format before implementation.

### Important Considerations

**5. "Sender ID (hex)" — does "hex" mean `0xABCD1234` or `ABCD1234`?**
- The Open Question 7 proposal uses `0xABCD1234` (C-style). Goal 2 says "(hex)". Scenario A
  says "sender ID `0xABCD1234`". But the filter input is described as "typed as 8 hex digits"
  (no `0x` prefix). Consistency needed: display format vs. filter input format.
- Question: Is the `0x` prefix shown in the log? Does the filter accept `0x` prefix or reject it?

**6. "Pause" — does the header or footer reflect the paused state?**
- Open Question 4 lists three UX options for communicating pause state (banner, header, footer).
  This is unresolved. Goal 4 ("Key bindings work reliably: `p` — pause/resume") says nothing
  about UI feedback.
- Why this matters: Without a decision, there will be no test for it.
- Question: Which pause indicator design is accepted?

**7. Base ID display: "add base ID (from dongle or `–` if unknown)"**
- Rough Approach says the base ID is shown in the header "or `–` until resolved". Open Question 2
  asks whether to issue the base-ID request in Phase 1.
- This is an unresolved design decision masquerading as a rough approach.
- Question: Is base ID retrieval in scope for Phase 1? Yes/no, with consequences for the header
  widget spec.

### Observations

- "Demo-able in 60 seconds" (Constraints) conflicts with "auto-reconnect from Phase 0 continues
  to work" if reconnect involves a serial port open delay. What is "60 seconds" measuring?
  First telegram visible, or app window open?
- "FakeDongle replay path works" (Goal 6) is passive voice — "works" against which test?
  Scenario C describes it informally but no formal test case is defined for this goal.
- Constraint "No new runtime dependencies without a clear reason" uses vague language. If an
  engineer adds a dependency with a reason they find clear but others don't, who adjudicates?
  Consider "no new runtime dependencies without Witness approval" or just remove the constraint
  as covered by code review.

## Confidence Assessment

**Medium-Low.** The pause semantics and filter interaction model are the two most ambiguous areas
and both will require a decision before the first implementation branch is opened. The log line
format decision can be deferred one sprint but must be resolved before integration tests are
written.
