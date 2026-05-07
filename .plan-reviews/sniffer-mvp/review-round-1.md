# Plan Self-Review Round 1 — Completeness + Sequencing

**Design doc:** `.designs/sniffer-mvp/design-doc.md`
**Date:** 2026-05-07
**Bead:** eat-wfs-pz662

---

## Completeness Review (eat-wfs-pz662.1 — polecat shiny)

Full report in `.plan-reviews/sniffer-mvp/completeness-round-1.md`.

### Applied fixes

**MUST-FIX (all 5 applied):**
- M1: `burst-300.jsonl` must contain ≥2 RORG types; task 17 updated to require 4BS (0xA5) entries
- M2: Task 16 path error — `Path(__file__).parent.parent` from `app.py` resolves to `src/`; fixed to three `.parent` hops (or `importlib.resources` for installed packages)
- M3: `FormattedTelegram.rssi_dbm` changed to `int | None`; `"N/A"` render rule added to §3.2 and task 6
- M4: Task 6 formatter spec corrected from `t.rssi` → `t.rssi_dbm`
- M5: `test_filter_live` added to §6 integration test table

**SHOULD-FIX (S1+S2 applied):**
- S1: `_buffer` changed from unbounded `list` to `deque(maxlen=10_000)` in §3.3 and task 5
- S2: Auto-discovery tests named and added to §6 as dedicated table section

---

## Sequencing Review (eat-wfs-pz662.2 — polecat guzzle)

### Applied fixes

**MUST-FIX (all 4 applied):**

- M1 **Task 2/3 swap (Phase 1-A):** `messages.py` (TelegramReceived) moved to task 2; `SnifferWorker` moved to task 3. SnifferWorker imports `TelegramReceived` — it cannot compile without it.

- M2 **Task 6/5 swap (Phase 1-B):** `formatters.py` moved to task 4 (first in Phase 1-B); `SnifferScreen` remains task 5. SnifferScreen declares `_buffer: deque[FormattedTelegram]` and calls `format_telegram()` — requires formatters to exist first.

- M3 **App wiring moved to end of Phase 1-B (task 6):** "Wire into `App.on_mount`" was Phase 1-A task 4; moved after `SnifferScreen` (task 5). When the worker starts, it immediately posts `TelegramReceived` messages — if SnifferScreen is not yet mounted as the active screen, those messages have no handler. Wiring now explicitly states it mounts SnifferScreen alongside starting the worker.

- M4 **Fixture before FakeDongle fix (Phase 1-E):** `burst-300.jsonl` update moved to task 14 (before tasks 15–17). Task 17 (FakeDongle modal fix) hardcodes the fixture path — the file must exist before that task is written or tested.

**SHOULD-FIX (both applied):**

- S1 **Tasks 15/16/17 labelled as parallel branches:** Added callout block between task 14 and task 15 noting that tasks 15, 16, 17 (one dongle / multiple / none) are independent branches of task 13's scan result and may be implemented in any order or concurrently.

- S2 **TDD cross-reference added to §5 header:** Added `> **TDD applies throughout:**` note at the top of §5 pointing to §6.

**Additional fix (data model ambiguity):**
- §3.4 corrected: `_pause_buffer` type changed from `deque[FormattedTelegram]` to `deque[RawTelegram]`. The §3.1 SnifferWorker code buffers raw telegrams from `DongleService.telegrams()` — `FormattedTelegram` in §3.4 was incorrect and would have created a hidden Phase 1-A → Phase 1-B dependency (worker needing formatters.py before it exists).

---

## Final task order (§5 after both reviews)

| Task | Phase | Description |
|------|-------|-------------|
| 1 | 1-A | workers/__init__.py |
| 2 | 1-A | messages.py (TelegramReceived) |
| 3 | 1-A | sniffer.py (SnifferWorker) |
| 4 | 1-B | formatters.py |
| 5 | 1-B | screens/sniffer.py (SnifferScreen) |
| 6 | 1-B | Wire App.on_mount (mount screen + start worker) |
| 7–10 | 1-C | Key bindings (q/c/p/f) |
| 11–12 | 1-D | Header extension (port + base-ID) — independent of 1-A/B/C |
| 13 | 1-E | Serial port scanner |
| 14 | 1-E | Update burst-300.jsonl fixture |
| 15–17 | 1-E | Auto-connect / modal / FakeDongle fix (parallel branches) |

**Critical path:** 1 → 2 → 3 → 4 → 5 → 6 → 7–10

Phase 1-D and Phase 1-E are off the critical path and can proceed in parallel with 1-A/B/C.

**No circular dependencies** found in either review.
