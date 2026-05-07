# Ambiguity Analysis

## Summary

The PRD is clearly written and well-scoped for a v0.1 spec. Most ambiguities are
acknowledged in the Open Questions section — but several of those questions remain
explicitly unresolved, which means implementation will hit them immediately. Beyond
the open questions, there are two genuine contradictions (data-loss semantics and
threading model), several underspecified UI interactions (filter input, pause UX,
`Escape` behavior), and a handful of undefined terms (`RawTelegram`, `DeviceManager`,
Phase 0.5) that will cause PR debates.

The biggest risk is the "no data lost" vs 256-entry queue contradiction: two engineers
reading this PRD would make opposite choices on what to do when the pause buffer fills.
Resolving that plus the six unresolved Open Questions should happen before work starts.

---

## Findings

### Critical Gaps / Questions

**1. "No data lost" vs DongleService queue bound of 256 — direct contradiction**

- Goal 4 (`p` binding): "telegrams queue while paused, no data lost"
- Scenario D: "No telegrams were dropped while paused (within the DongleService
  queue bound of 256)"

These cannot both be universally true. One engineer will implement an unbounded
pause buffer to honour "no data lost"; another will cap it at 256 and consider the
parenthetical the real spec. A third will propagate back-pressure to the caller.

*Suggested clarifying question:* "When more than 256 telegrams arrive during a
pause, should the app drop the oldest, drop the newest, or is 256 enough that this
never happens in practice? What is the expected user behaviour?"

---

**2. `threading.Event` vs asyncio constraint — contradiction in Rough Approach**

- Constraint: "Async-only… no blocking I/O on the event loop thread"
- Rough Approach: "worker checks a `threading.Event` (or asyncio-compatible flag)"

`threading.Event.wait()` is blocking. The "or asyncio-compatible flag" hedge
acknowledges this but leaves the choice open. These are meaningfully different
implementations; mixing them with Textual's worker model can introduce subtle
blocking.

*Suggested clarifying question:* "Should the pause flag be `asyncio.Event` (clean,
non-blocking, asyncio-native) or `threading.Event` (only safe with
`asyncio.to_thread`)? This determines the worker's concurrency model."

---

**3. "raw payload hex" — what bytes are included?**

Goal 2 says "raw payload hex" but doesn't specify boundaries. An EnOcean packet has:
RORG byte, data bytes, sender ID bytes, status byte, optional CRC. "Payload" could
mean:
- Only the data bytes (excluding RORG, sender ID, status, CRC)
- Everything after RORG up to the CRC
- The full packet bytes

Open Question 7 shows a proposed log line (`70`) that looks like a single byte, but
`RPS` data is 1 byte, `4BS` is 4 bytes — the column width varies. Truncation vs full
display is flagged in OQ7 but not resolved.

*Suggested clarifying question:* "Which bytes does 'raw payload hex' cover — data
bytes only, or full packet minus RORG and sender ID? And is truncation allowed?"

---

**4. "within 100 ms of the command starting" — starting from when?**

Goal 1: "see a live, scrolling log… within 100 ms of the command starting."

"Command starting" is ambiguous:
- Process spawn (Python import time alone may exceed 100 ms on slow hardware)
- UI rendered and ready
- First telegram received and displayed
- Serial port successfully opened

If this is a latency SLO it needs a precise start and end event.

*Suggested clarifying question:* "Is the 100 ms target for (a) UI becoming interactive
after process start, or (b) first telegram appearing after the serial port is open?
And is this a hard requirement or a goal?"

---

**5. Filter mode: retroactive or prospective? Toggle semantics?**

Goal 4 (`f`): "enter filter mode (show only a given sender ID)". Open Question 5
says filter is "cleared with `f` again or `Escape`."

Unclear:
- Does applying a filter hide already-displayed log lines, or only affects new
  arrivals? (Two engineers will disagree loudly on this.)
- Pressing `f` when filter is active: does it toggle off the filter, or open the
  input again to change it?
- `Escape` during filter entry with no text typed: clears filter, or cancels entry
  (leaves previous filter active)?

*Suggested clarifying question:* "When a filter is applied, are existing log lines
hidden/re-filtered, or only future telegrams filtered? What does pressing `f` do
when a filter is already active?"

---

**6. Phase 0.5 is mentioned in bead context but absent from the PRD**

The bead description says: "Spec and implement Phase 0.5 (frame capture tool) and
Phase 1 (Sniffer MVP)". Phase 0.5 is not mentioned anywhere in the PRD. This could
mean:
- Phase 0.5 is a separate PRD/spec to be written
- Phase 0.5 requirements are folded into Phase 1 without labelling
- The PRD title and scope cover Phase 1 only, and Phase 0.5 is out-of-scope here

*Suggested clarifying question:* "Is Phase 0.5 (frame capture tool) covered by this
PRD, or is there a separate spec? If it's in scope, where are its requirements?"

---

### Important Considerations

**7. Six Open Questions are explicitly unresolved**

Questions 1–7 are all outstanding. Of these, 5 have direct implementation impact:
- **OQ1** (log retention): 10 000 lines is a candidate but not decided. Code that
  hard-codes any other value will be wrong or need rework.
- **OQ2** (base ID retrieval): deferred to Phase 2 or not? This changes what the
  sniffer worker does on connect.
- **OQ3** (RSSI display): raw dBm vs icons — affects widget layout width.
- **OQ4** (pause UX): banner / header / footer colour — affects which widget to add.
- **OQ5** (filter: single vs multi): already settled to single ID in OQ5 body, but
  the filtering widget design differs if that changes.
- **OQ6** (RORG name vs hex): proposal exists ("name + hex in parentheses") but is
  not marked as decided.

These should be closed before Step 3 of the formula.

---

**8. Pause deque bounds are unspecified**

Rough Approach: "buffers telegrams in a local `deque` while paused". No capacity is
specified. If unbounded, long pauses on a busy bus will grow memory without limit. If
the deque is bounded separately from the DongleService 256-item queue, the total
buffer is additive and the data-loss semantics become even less clear (see item 1).

---

**9. `DeviceManager` is referenced without definition**

Goal 7: "integration (DeviceManager or sniffer worker + FakeDongle)". `DeviceManager`
appears nowhere else in the PRD. This could be a future component, a holdover from an
earlier design, or a synonym for the sniffer worker. An implementor writing the
integration test scaffold will not know which to use.

---

**10. Filter input validation is unspecified**

Open Question 5: "typed as 8 hex digits". No guidance on:
- Whether the `0x` prefix is allowed or rejected
- Whether input is case-sensitive (`abcd1234` vs `ABCD1234`)
- What happens if fewer than 8 digits are entered (reject, zero-pad, live filter?)
- Whether the Input widget prevents non-hex characters or shows an error after

---

**11. `c` (clear) while paused — interaction undefined**

The PRD specifies `c` clears the log and `p` pauses with queued telegrams. There is no
description of what `c` does when the app is paused:
- Does it clear only the visible log, leaving the pause buffer intact?
- Does it also flush (discard) the pause buffer?
- After pressing `c` while paused, does resuming show the queued telegrams or a fresh empty log?

---

**12. "reliably" in key bindings is not quantified**

Goal 4: "Key bindings work reliably". This is unmeasurable without a definition. Does
it mean "works in all cases" (functional requirement), "no missed keys under load"
(performance), or "all bindings are always visible in the footer" (discoverability)?

---

**13. Coverage gate scope and type**

Goal 8: "Coverage gate stays ≥ 80%". Not specified:
- Line coverage, branch coverage, or combined?
- Whole-project coverage or only code added in Phase 1?
- Enforcement mechanism (CI step, `pytest --cov` threshold flag)?

---

### Observations

**14. "additions only" vs "Main pane is replaced"**

Constraint: "Phase 0 foundation is fixed… Additions only." Rough Approach: "Main
pane is replaced with a `RichLog` widget." Replacing a widget is structurally
different from adding one. If the Phase 0 app shell hard-codes the main pane widget
type, this is a modification, not an addition. Worth confirming Phase 0 left a
placeholder or blank pane.

---

**15. FakeDongle "pressing a recorded switch" is physically unmappable**

Scenario C: "She accepts 'Fake dongle mode'. The sniffer shows replayed telegrams
from a recorded session fixture." But Goal 6: "pressing a recorded switch replays
correctly". In a TUI without hardware, what user action triggers the replay? A key
binding? Automatic on startup? The test in Rough Approach says "FakeDongle replays 3
telegrams" which implies automatic replay, but the scenario implies user-triggered.

---

**16. Timestamp format and timezone**

Open Question 7 proposes `14:23:01.042` (local wall-clock, millisecond precision) but
does not specify:
- UTC or local time zone
- Whether to include date for sessions crossing midnight
- Monotonic vs wall-clock (matters for replay accuracy)

---

**17. `q` during filter input**

The PRD does not specify whether the global `q` (quit) binding is active while the
filter `Input` widget has focus. If it is, accidental quitting while typing an ID
starting with `q...` is likely.

---

**18. "Demo-able in 60 seconds" start state is undefined**

Constraint: "A first-time user can go from zero to live sniffer in under a minute."
"Zero" is ambiguous — zero means after `uv` is installed, or also include installing
`uv`? Does it require a connected dongle? The FakeDongle path (no hardware) is the
only universally reproducible demo path, so this constraint implicitly tests Scenario C.

---

**19. "should" vs "must" usage is inconsistent**

The constraints section uses "must" for most requirements, but Goal 8 says
"Coverage gate stays ≥ 80%. CI gate stays green" — stated as a plain fact, not as
"must" or "should". This makes it unclear whether it's a hard gate (blocks merge) or
a monitoring target.

---

## Confidence Assessment

**Medium.** The PRD is coherent and well-structured, but the six explicitly open
questions are unresolved and at least two genuine contradictions exist (data-loss
semantics, threading model). The core sniffer loop, display format, key bindings,
and test strategy are all described — but implementation will stall at the filter
widget design, pause buffer semantics, and log line format without answers to OQs
1, 3, 4, 5, 6, and 7. Resolving those plus the contradiction in item 1 would raise
confidence to High.
