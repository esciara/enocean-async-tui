# Plan Self-Review Round 3 — Testability + Coherence

**Design doc:** `.designs/sniffer-mvp/design-doc.md`
**Date:** 2026-05-07
**Bead:** eat-wfs-7wlyy

---

## Testability Review

### MUST-FIX

**T4: No test for `q` key binding**
- PRD Goal 4 lists `q` as a required key binding. The integration test table covers
  `c`, `p`, and `f` but omits `q`. TDD requires a failing test before implementation.
- Applied fix: Added `test_quit_binding` to integration test table — Press `q`; assert
  app exits cleanly.

**T7: No test for header extension (Phase 1-D)**
- PRD Goal 3 requires header to show port and base-ID `–`. Phase 1-D (tasks 11–12)
  adds this to the header but no test is specified anywhere in §6.
- Applied fix: Added `test_header_content` to integration test table — Start with
  `--port /dev/ttyUSB0`; assert header shows port and `–` for base-ID.

### SHOULD-FIX

**T1: `test_reconnect_resumes_streaming` too vague**
- The assertion "Worker re-enters telegram loop after DongleDisconnected + reconnect event"
  doesn't specify how the reconnect event is injected, or that the event-based mechanism
  (not polling) is specifically verified.
- Applied fix: Assertion updated to "...reconnect asyncio.Event fired via DongleService
  mock; no busy-polling".

**T2: Spike result (task 4.5) not CI-verifiable**
- Task 4.5 says "Document in a code comment" but a code comment can't be checked by CI.
  If the threshold is later exceeded, no automated signal catches it.
- Applied fix: Added optional `@pytest.mark.slow` benchmark in
  `tests/perf/test_richlog_batch.py` recommendation to task 4.5.

**T3: No test for `SnifferScreen._buffer` maxlen boundary**
- The plan specifies `deque(maxlen=10_000)` for the screen's `_buffer`, but no test
  verifies the boundary. Overflow silently drops oldest entries; a wrong maxlen would
  cause memory growth with no visible failure.
- Applied fix: Added `test_buffer_maxlen` to unit test table
  (`tests/unit/test_sniffer_screen.py`).

**T5: No test for PAUSED banner text accuracy**
- The pause banner ("PAUSED — N queued", "N dropped" on overflow) is UI-visible state
  described in task 9. No test checks the banner text content.
- Applied fix: Added `test_pause_banner` to integration test table.

**T6: `test_filter_enter` doesn't verify "pending" CSS class**
- The scenario tests "log updates only on Enter" but not the intermediate state while
  typing (pending CSS class). Without this assertion the pending style could be broken
  with tests still passing.
- Applied fix: Updated `test_filter_enter` assertion to include "pending CSS class
  present during typing; removed after Enter".

**T8: No CI validation of fixture contents (task 14)**
- Task 14 updates `burst-300.jsonl` to add 4BS entries but has no automated check.
  A future edit could reduce the fixture back to single-RORG without any CI signal.
- Applied fix: Added companion test `test_fixture_contents` in
  `tests/unit/test_fixtures.py` to the auto-discovery test table; added note to task 14.

**T9: Coverage gate specifies 80% but no measurement command**
- `uv run pytest` alone doesn't report coverage. Without `--cov` flags the ≥80% gate
  is aspirational, not enforced.
- Applied fix: Updated quality gates to
  `uv run pytest --cov=src/enocean_async_tui --cov-fail-under=80`.

**T10: No end-to-end test for Scenario C**
- PRD Scenario C (no port → auto-discovery → FakeDongle modal → sniffer shows telegrams)
  is only partially covered. `test_autodiscovery_no_dongle` checks discovery; task 17 is
  exercised by `test_live_display`; but the full chain (modal accept → sniffer receives
  replayed telegrams) has no single end-to-end test.
- Applied fix: Added `test_scenario_c_e2e` to integration test table.

---

## Coherence Review

### MUST-FIX

**C1: Ambiguous pause flush path bypasses filter**
- §3.4 said "flush `_pause_buffer` to `_buffer` and `RichLog` in order" — this could be
  read as the worker writing directly to the screen's `_buffer`, bypassing the
  `on_TelegramReceived` handler. The filter (§3.3) is applied in that handler. A direct-
  write flush would silently show all paused telegrams regardless of the active filter,
  which is a correctness bug.
- Applied fix: §3.4 Pause-off now specifies "flush by posting `TelegramReceived(telegram)`
  for each entry in order — the screen's `on_TelegramReceived` handler applies the active
  filter... (Direct-write bypass would silently skip the filter.)"

### SHOULD-FIX

**C2: §3 architecture diagram omits PausedBanner widget**
- Task 9 adds a PAUSED banner (`Static`/`Label` widget) overlaid on the log pane.
  The §3 architecture diagram shows `SnifferScreen` with `RichLog` and `FilterInput`
  but omits the banner. A developer reading the diagram would miss this component.
- Applied fix: Added `PausedBanner widget` entry to the §3 architecture diagram.

**C3: Task 10 omits `f`-again behavior for clearing filter**
- §3.3 says "`f` again or `Escape` clears filter" but task 10 only specifies Escape as
  the clear action. A developer implementing task 10 would not know to handle `f`-again.
- Applied fix: Task 10 updated to "on Escape (or `f` again while input is visible)".

**C4: Integration test table lacks file paths**
- The unit test table specifies file paths per test. The integration test table had no
  file column, leaving developers uncertain where to create test files.
- Applied fix: Added note "All integration tests live in
  `tests/integration/test_sniffer.py` unless noted." above the integration test table.

---

## Applied Fixes Summary

| ID | Severity | Section | Change |
|----|----------|---------|--------|
| T4 | MUST-FIX | §6 integration tests | Added `test_quit_binding` |
| T7 | MUST-FIX | §6 integration tests | Added `test_header_content` |
| C1 | MUST-FIX | §3.4 pause-off | Specified flush via `TelegramReceived` message path |
| T1 | should-fix | §6 unit tests | Clarified `test_reconnect_resumes_streaming` assertion |
| T2 | should-fix | §5 task 4.5 | Added optional `tests/perf/test_richlog_batch.py` benchmark |
| T3 | should-fix | §6 unit tests | Added `test_buffer_maxlen` |
| T5 | should-fix | §6 integration tests | Added `test_pause_banner` |
| T6 | should-fix | §6 integration tests | Updated `test_filter_enter` with CSS class assertion |
| T8 | should-fix | §5 task 14 + §6 auto-discovery | Added `test_fixture_contents`; note added to task 14 |
| T9 | should-fix | §6 quality gates | Added `--cov=src/enocean_async_tui --cov-fail-under=80` |
| T10 | should-fix | §6 integration tests | Added `test_scenario_c_e2e` |
| C2 | should-fix | §3 architecture | Added `PausedBanner widget` to SnifferScreen diagram |
| C3 | should-fix | §5 task 10 | Added `f`-again as filter-clear action |
| C4 | should-fix | §6 integration tests | Added file location note above table |

Total: 3 must-fix, 11 should-fix → **14 fixes applied**
