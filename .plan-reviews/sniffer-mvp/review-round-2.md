# Plan Self-Review Round 2 — Risk + Scope-Creep

**Design doc:** `.designs/sniffer-mvp/design-doc.md`
**Date:** 2026-05-07
**Bead:** eat-wfs-m72dw

---

## Risk Review (Polecat A)

### MUST-FIX

**R1: Batch re-render of 10K entries may block the event loop**
- Impact: HIGH | Likelihood: MEDIUM
- Mitigation: must-fix
- §10 claims "RichLog.clear() + batch append is fast" — unverified. 10K sequential
  `write_markup()` calls in a tight sync loop will monopolise the asyncio event loop for
  the entire duration; the UI freezes until complete.
- Suggested action: Add a spike task before Phase 1-B task 5.
  Benchmark `RichLog.write_markup()` × 10K entries. If >200 ms, implement chunked flush:
  write in batches of 100–200 with `await asyncio.sleep(0)` between batches to yield
  control back to the event loop between chunks.

**R2: `_wait_for_reconnect()` implementation is unspecified**
- Impact: MEDIUM | Likelihood: HIGH
- Mitigation: must-fix
- §3.1 calls `await self._wait_for_reconnect()` after `DongleDisconnected`, but neither
  §3.1 nor any task specifies how the method is implemented. If it polls
  `DongleService.state` in a loop with `asyncio.sleep(0.1)` it is a busy-poll. If it
  subscribes to a `DongleService` event, the exact API needs to be pinned.
- Suggested action: Specify in §3.1 that `_wait_for_reconnect()` awaits a
  `asyncio.Event` (or equivalent mechanism already provided by `DongleService` in Phase 0)
  that fires when the dongle reconnects. Reference the Phase 0 state-change API explicitly
  in task 3 so the implementer knows exactly what to call.

### SHOULD-FIX

**R3: `RawTelegram.rssi_dbm` property existence not verified against enocean-async**
- Impact: MEDIUM | Likelihood: LOW
- Mitigation: should-fix
- Task 4 assumes `RawTelegram` exposes a `.rssi_dbm: int | None` property. This
  property was mandated in Round 1 completeness review (M3), but the actual
  `enocean-async` library version in use may expose a different attribute name (e.g.,
  `.rssi` returning raw bytes or a uint8, not a signed int). If wrong, `format_telegram()`
  breaks at runtime with an `AttributeError`.
- Suggested action: Add a verification note to task 4: "Confirm `RawTelegram.rssi_dbm`
  exists in the installed version of `enocean-async`. If missing, derive via
  `(t.rssi if t.rssi != 0xFF else None)` and open a bead to upstream the property."

**R4: Textual Worker cancellation may suppress `asyncio.CancelledError`**
- Impact: MEDIUM | Likelihood: LOW
- Mitigation: should-fix
- The outer retry loop catches `DongleDisconnected`. If any `except` clause is too broad
  (e.g., `except Exception`) it will swallow `asyncio.CancelledError`, preventing clean
  Worker shutdown on app exit or screen unmount.
- Suggested action: Tighten the `except` clause in §3.1's outer loop to only catch
  `DongleDisconnected` (and potentially `asyncio.TimeoutError` if relevant). Never use
  bare `except` or `except Exception` in async Workers. Add note to §3.1.

---

## Scope-Creep Review (Polecat B)

### MUST-FIX

None. The plan is well-scoped to the PRD.

### SHOULD-FIX

**SC1: `importlib.resources` packaging path in task 17 — defer**
- Classification: DEFER
- The final paragraph of task 17 describes adding the fixture to
  `src/enocean_async_tui/data/` and using `importlib.resources` for installed-package
  support. This requires: updating `pyproject.toml` package-data config, restructuring
  the fixture location, and additional test coverage for the installed path. None of
  this is required for a demo or development checkout.
- Suggested action: Remove the `importlib.resources` paragraph from task 17. Leave only
  the three-`.parent` dev-checkout path with a `# TODO: use importlib.resources for
  installed-package support (Phase 2 packaging)` comment.

**SC2: Multi-dongle selection modal (task 16) — simplify**
- Classification: SIMPLIFY
- Task 16 calls for a "selection modal (user picks one dongle)" when `comports()` returns
  multiple matching dongles. Building a new Textual modal widget is non-trivial UI work.
  The Phase 0 FakeDongle modal already provides a model for a choice dialog; task 16
  should explicitly reuse that pattern rather than building from scratch.
- Alternatively: for Phase 1 MVP, auto-connect to the first dongle found and show a
  non-blocking status message in the header (e.g., "Multiple dongles found; using
  /dev/ttyUSB0"). The user can always re-run with `--port` to override.
- Suggested action: Revise task 16 to either (a) reuse the existing Phase 0 modal
  skeleton for consistency, or (b) simplify to auto-first-found + header warning.
  Either approach eliminates a new UI component.

---

## Applied Fixes

### §10 Risk table

- R1: Strengthened existing "Retroactive filter re-render slow" entry — mitigation changed
  from vague "is fast" claim to concrete spike task recommendation.
- R2: Added new row for `_wait_for_reconnect()` unspecified implementation.
- R3: Added new row for `rssi_dbm` property verification.
- R4: Added cancellation note to existing "Textual Worker lifecycle vs asyncio Event" entry.

### §3.1 SnifferWorker

- Added explicit note on `CancelledError` handling (R4).
- Added requirement that `_wait_for_reconnect()` must use the Phase 0 DongleService
  state-change API, not poll (R2).

### §5 Implementation Tasks

- Spike task added before task 5 (Phase 1-B): benchmark RichLog batch-write (R1).
- Task 3: Added note to reference DongleService reconnect API (R2).
- Task 4: Added verification note for `rssi_dbm` property (R3).
- Task 16: Simplified — reuse Phase 0 modal pattern (SC2).
- Task 17: Removed `importlib.resources` paragraph; left dev-path only with TODO (SC1).
