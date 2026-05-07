# PRD Alignment Round 1: Requirements + Goals
## Phase 1 Sniffer MVP

**PRD:** `.prd-reviews/sniffer-mvp/prd-draft.md`
**Plan:** `.designs/sniffer-mvp/design-doc.md`
**Reviewer:** nitro (combined A + B — sling unavailable to polecats)
**Date:** 2026-05-07

---

## Part A — Requirements Coverage

### Goals

| # | Requirement | Status | Notes |
|---|-------------|--------|-------|
| G1 | Live scrolling log, no perceptible display lag | COVERED | §3.1 SnifferWorker posts TelegramReceived → single async loop hop to RichLog |
| G2 | Log line: ISO-8601-ms ts · 0xID · RORG(hex) · payload-hex · RSSI dBm | COVERED | §3.2 FormattedTelegram + §1-B formatters.py match clarification Q5 exactly |
| G3 | Header: title · status · port · base-ID (–) | COVERED | §1-D extends header; §7 confirms base ID = "–" |
| G4 | Keys: q · c · p · f with clarified pause/clear semantics | COVERED | §1-C all 4 keys; §3.4 matches clarifications Q1+Q2; §3.3 matches Q3+Q4 |
| G5 | Auto-reconnect continues | **PARTIAL** | SnifferWorker reconnect recovery not described — see must-fix below |
| G6 | FakeDongle replay works in sniffer | COVERED | §6 tests use FakeDongle; DongleService API unchanged |
| G7 | Integration + UI Pilot tests pass | COVERED | §6 Test Plan covers both layers; decoder-unit N/A per PRD |
| G8 | Coverage ≥ 80%, CI green | **PARTIAL** | No explicit coverage gate in design — see should-fix below |

### Constraints

| Constraint | Status | Notes |
|------------|--------|-------|
| C1: Async-only, no blocking I/O | COVERED | §3.1 `@work` coroutine; asyncio.Event — never blocks event loop |
| C2: Single event loop | COVERED | §9 Dependencies: asyncio.Event (same loop); risk listed in §10 |
| C3: Phase 0 API fixed | COVERED | §4.1 explicitly states no changes to DongleService/FakeDongle/Settings |
| C4: No new runtime deps without reason | COVERED | §9 "No new runtime dependencies" |
| C5: TDD non-negotiable | **GAP** | No mention of TDD order-of-operations in design doc |
| C6: mypy strict must stay clean | **GAP** | No mention of mypy in design doc quality gates |
| C7: Demo-able in 60 seconds | PARTIAL | §1-E auto-discovery addresses friction; 60s goal not mentioned explicitly |

### Clarifications (all must be reflected)

| Q# | Clarification | Status |
|----|---------------|--------|
| Q1 | Pause buffer = bounded deque 256, ring-buffer semantics | COVERED | §3.4 exactly |
| Q2 | `c` while paused clears log + buffer | COVERED | §3.4 exactly |
| Q3 | Filter retroactive from in-memory buffer | COVERED | §3.3 exactly |
| Q4 | Filter applies on Enter, pending visual state | COVERED | §3.3 exactly |
| Q5 | Exact log line format with 0x prefix, ISO 8601 ts | COVERED | §3.2 + §1-B |
| Q6 | Port not found → auto-discover, then FakeDongle modal | COVERED | §1-E + §4.2 |
| Q7 | 100ms = display latency, not cold-start | COVERED | §2 G1 note |
| Q8 | Base ID deferred → shows "–" in Phase 1 | COVERED | §2 G3 + §7 |

### User Scenarios

| Scenario | Status | Notes |
|----------|--------|-------|
| A (Debug with filter) | COVERED | Retroactive filter per §3.3; sender-ID filter per §1-C |
| B (Identify unknown devices) | COVERED | Log shows sender IDs; user copies them |
| C (Demo without hardware) | COVERED | §1-E auto-discovery → FakeDongle modal |
| D (Pause and inspect) | COVERED | §3.4 pause semantics; flush on resume |

---

## Part B — Goals Alignment

| Goal | Status | Assessment |
|------|--------|------------|
| G1: Display latency ≤100ms | ALIGNED | Single async hop: TelegramReceived → App.on_message → RichLog.write_markup. No off-loop threads. Well under 100ms under any realistic telegram rate. |
| G2: Exact log line format | ALIGNED | FormattedTelegram fields map 1:1 to clarification Q5. Test `test_format_telegram` validates the exact string. |
| G3: Header fields | ALIGNED | Phase 0 already drives title + status. Phase 1 adds port from Settings + "–" for base ID. |
| G4: Key bindings + pause/filter semantics | ALIGNED | All 4 keys covered. Pause deque 256 + overflow counter + clear-while-paused all explicitly modelled in §3.4 and §3.3. |
| G5: Auto-reconnect | **MISALIGNED** | The design says "worker re-subscribes" but does not describe the mechanism. If `async for telegram in service.telegrams()` exits when the dongle disconnects, the sniffer loop terminates. Nothing in the design restarts it after a reconnect event. Without an explicit reconnect recovery loop, Goal 5 will fail silently in practice. **must-fix** |
| G6: FakeDongle replay | ALIGNED | Same DongleService interface; FakeDongle replays pre-recorded telegrams. Tests confirm. |
| G7: Tests pass | ALIGNED | §6 covers unit + integration (FakeDongle Pilot). Decoder-unit N/A per PRD. |
| G8: Coverage + CI | PARTIAL | Test plan is comprehensive but does not address the coverage gate explicitly. Auto-discovery code (§1-E) has conditional paths that could miss 80% without targeted tests. **should-fix** |

---

## Findings Summary

### MUST-FIX

**M1 — G5: SnifferWorker reconnect recovery path not specified**

The plan says "DongleService handles reconnect; sniffer worker re-subscribes" but provides
no mechanism. Risk: after a real dongle unplug/replug cycle, `DongleService.telegrams()`
will raise or return; the worker exits; the sniffer silently goes dark even though the
header shows "connected."

**Required fix:**
- §3.1 must describe a reconnect loop pattern:
  ```python
  async def run(self) -> None:
      while not self._cancelled:
          try:
              async for telegram in self._service.telegrams():
                  ...
          except DongleDisconnected:
              await self._wait_for_reconnect()  # listens for state-change events
  ```
- The SnifferWorker must subscribe to the same DongleService state-change events
  already wired in Phase 0, and restart its iteration loop on reconnect.
- Add integration test: disconnect FakeDongle mid-stream, reconnect, assert streaming resumes.

---

### SHOULD-FIX

**S1 — C5: TDD constraint missing from design**

The PRD lists TDD as non-negotiable. The design describes WHAT to build and WHAT tests
to write, but nowhere states that tests are written first (red → green → refactor).
Add a "Quality Gates" section or note to §6 Test Plan:

> Tests must be written before the production code they exercise. No production code
> without a failing test that demanded it.

**S2 — C6: mypy strict not mentioned**

The PRD requires `mypy --strict` to stay clean. The design doc has no mention of mypy.
Add to quality gates: all new code must pass `uv run mypy` (strict). The `FormattedTelegram`
dataclass and `TelegramReceived` message must be fully typed.

**S3 — G8: Coverage gate not addressed**

The design's test plan is good but doesn't mention the ≥ 80% coverage gate. Auto-discovery
(§1-E) has several conditional branches. Add a note to §6:

> Coverage gate: ≥ 80% required. Auto-discovery paths must have targeted tests (mock
> serial scan). The FakeDongle integration tests count toward coverage.

**S4 — G1: 100ms latency note should reference architecture**

Goal 1 says "no perceptible lag." The design achieves this through a single event-loop
hop. Add a one-line architectural note in §3.1 confirming that no off-loop threads or
queues are in the hot path between DongleService.telegrams() and RichLog.write_markup().

---

## Actions Applied to Design Doc

- [x] M1: Added explicit reconnect recovery loop pattern to §3.1 SnifferWorker
- [x] M1: Added reconnect integration test to §6 Test Plan
- [x] S1: Added TDD constraint to §6 Test Plan header
- [x] S2: Added mypy strict requirement to §6 Test Plan
- [x] S3: Added coverage gate note to §6 Test Plan
- [x] S4: Added hot-path latency note to §3.1
