# Technical Feasibility

## Summary

Phase 1 is technically straightforward given the Phase 0 foundation. The hardest problem is the
100 ms startup latency target, which is tight for Python + serial initialisation. Everything else
is well within reach: `RichLog` is a Textual built-in, the `DongleService` async API is designed
for exactly this use case, and the FakeDongle path avoids hardware entirely. Two areas warrant
investigation before coding: RSSI availability in the `enocean-async` telegram model, and the
interaction between Textual's event dispatch and high-frequency telegram bursts.

## Findings

### Critical Gaps / Questions

**1. 100 ms startup latency target is likely unachievable cold**
- Python 3.14 startup time + uv process spawn + pyserial open + EnOcean handshake + Textual
  compose cycle is typically 500–1500 ms in practice.
- "Within 100 ms of the command starting" may actually mean "within 100 ms of the dongle being
  ready" (i.e., after connect), but the PRD is ambiguous.
- Why this matters: If this is a hard CI gate, it will fail on CI runners and frustrate
  developers. If it's marketing copy, it should say so.
- Question: Is the 100 ms target measured from process start or from first dongle frame received?
  Is it a tested SLA or an aspirational benchmark?

**2. RSSI availability per telegram in enocean-async is unverified**
- The PRD requires per-line RSSI in dBm. The `enocean-async` library wraps the ESP3 telegram
  format. RSSI is carried in the optional data section of an ESP3 packet, present only for
  telegrams received by the dongle (not for loopback/confirmation packets).
- Why this matters: If RSSI is absent for some telegram types, the formatter will need a
  fallback value. If the library doesn't expose it at all, a workaround or library patch is needed.
- Question: Verify that `enocean-async`'s telegram model exposes RSSI. Check the library source
  and file a blocker bead if RSSI is not available.

**3. Textual's RichLog performance under high-frequency telegram bursts**
- EnOcean traffic can burst (button press = several repeats). Textual's `RichLog.write()` is
  safe to call from a Worker, but very high call rates (>100 writes/second) can cause the UI to
  stutter because each write triggers a layout invalidation.
- Why this matters: A burst of 50 telegrams in 200 ms could make the UI freeze for a second.
- Question: Is rate-limiting or batching of `RichLog.write()` calls in scope? Define the max
  burst rate the UI must handle smoothly.

### Important Considerations

**4. Filter implementation: retroactive filter requires re-rendering the log**
- If the filter applies retroactively (as suggested by Scenario A, where Alice "watches the
  log … presses f … [and] the log now shows only that device"), this requires re-rendering all
  existing log lines, not just gating new ones.
- `RichLog` does not natively support filtering. Retroactive filtering means maintaining a
  parallel buffer of all received telegrams and re-populating the `RichLog` on filter change.
  This is a significantly larger implementation than prospective-only filtering.
- Suggestion: Decide prospective vs. retroactive before implementation. Retroactive is a larger
  scope.

**5. Asyncio event loop sharing between Textual Workers and enocean-async**
- Phase 0 already solved this (Workers share the Textual event loop). Phase 1 adds the sniffer
  Worker. The concern is: if `enocean-async` blocks for serial I/O even briefly, it starves the
  Textual event loop (UI freeze).
- `enocean-async` is async-first by design, so this is low risk — but verify the library uses
  `asyncio.StreamReader` / `asyncio.to_thread` and not `pyserial` blocking reads internally.
- Suggestion: Add a note to the architecture section confirming the I/O model.

**6. Pause buffer: asyncio queue vs. threading.Event**
- The Rough Approach mentions "threading.Event (or asyncio-compatible flag)". In an all-asyncio
  context, a `threading.Event` is safe to check but unsafe to wait on (it blocks the event loop).
  An `asyncio.Event` is the correct primitive.
- This is a common Python async anti-pattern and should be specified explicitly.
- Suggestion: Specify `asyncio.Event` for pause control, not `threading.Event`.

### Observations

- `enocean-async` is listed in requirements but its version is not pinned in the PRD. If the
  library's API changes between Phase 0 and Phase 1, the sniffer worker may need updates.
  Confirm the version used in Phase 0 is the intended Phase 1 version.
- The `RichLog` widget's built-in virtual scrolling handles the retention bound efficiently. A
  10 000-line cap is trivially achievable via `RichLog(max_lines=10000)`. This is low risk.
- Textual's Pilot testing framework is async-native and well-suited for the described test cases.
  Integration tests for the sniffer using FakeDongle are straightforward to implement.
- mypy strict compatibility with `enocean-async` needs verification — some async libraries have
  incomplete type stubs, which would require type ignore comments (violating the constraint).

## Confidence Assessment

**High.** Phase 1 is technically feasible on the existing stack. The RSSI availability check
and the retroactive-vs-prospective filter decision are the only items that could force a scope
change. The 100 ms target needs clarification but doesn't block implementation.
