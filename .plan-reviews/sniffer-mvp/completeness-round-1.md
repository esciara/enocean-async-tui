# Completeness Review Round 1: Infrastructure, Tests, Error Handling
## Phase 1 Sniffer MVP

**PRD:** `.prd-reviews/sniffer-mvp/prd-draft.md`
**Plan:** `.designs/sniffer-mvp/design-doc.md`
**Reviewer:** shiny (eat-wfs-pz662.1)
**Date:** 2026-05-07
**Based on:** Round 3 changes applied (eat-wfs-ayqsk)

**Scope:** Check for missing infrastructure setup, data migrations, test tasks,
documentation updates, error handling, rollback procedures, implicit dependencies,
and coarse-grained tasks.

---

## Checklist

| Category | Status | Summary |
|----------|--------|---------|
| Infrastructure setup | OK | CI exists (`.github/workflows/ci.yml`), `pytest-cov` configured, pre-commit hooks in place |
| Data migrations | N/A | TUI app — no persistent database |
| Test tasks | **GAPS** | M5 (live-filter test missing), S2 (auto-discovery tests not named) |
| Documentation updates | OK | README exists; no new CLI surface that changes usage |
| Error handling | **GAPS** | M3+M4 (RSSI None + wrong attr name), S3 (FilterInput validation) |
| Rollback procedures | N/A | Phase 1 is additive-only; Phase 0 is unmodified |
| Implicit dependencies | **GAPS** | M1 (fixture RORG coverage), M2 (path bug) |
| Coarse-grained tasks | OK (minor) | S5 (Task 5 large but manageable) |

---

## Findings

### MUST-FIX

**M1 — `burst-300.jsonl` covers only 1 RORG type (fixture spec violation)**

`tests/fixtures/recordings/burst-300.jsonl` (300 entries, 20 sender IDs) contains
only RORG 0xF6 (RPS). Task 17 requires "≥2 RORG types (e.g. RPS and 4BS)."

Without a second RORG type:
- `test_rorg_lookup` cannot verify 4BS name formatting
- `test_live_display` and `test_filter_retroactive` only exercise RPS code paths
- The auto-discovery integration tests that reference multi-RORG coverage are broken at fixture level

**Suggested fix:** Add 10–20 entries with RORG 0xA5 (4BS) covering a distinct sender ID.
A minimal 4BS frame is: `a5` + 4-byte data + 4-byte sender + 1-byte status = 10 bytes hex.
Example entry: `{"t_offset_ms": 5, "telegram_hex": "a500000000BBBBBBB130", "rssi_dbm": -70}`.

Applied to design doc: Task 17 updated to note that the file exists but needs 4BS entries.

---

**M2 — Recording path in task 16 is one `.parent` level short**

`Path(__file__).parent.parent` from `src/enocean_async_tui/app.py` resolves to `src/`,
not the project root. The tests fixture lives at `<project-root>/tests/fixtures/...`.

Calling `fake = FakeDongle(recording=Path(__file__).parent.parent / "tests/fixtures/...")` at
runtime would produce a `FileNotFoundError` (path `src/tests/fixtures/...` does not exist).

**Suggested fix (dev mode):** Use `Path(__file__).parent.parent.parent / "tests/fixtures/recordings/burst-300.jsonl"`.

**Suggested fix (installed packages):** Bundle the recording as package data in
`src/enocean_async_tui/data/burst-300.jsonl` and use
`importlib.resources.files("enocean_async_tui").joinpath("data/burst-300.jsonl")`.

Applied to design doc: Task 16 corrected to three `.parent` hops with note on both approaches.

---

**M3 — `FormattedTelegram.rssi_dbm: int` — wrong type; None case unspecified**

`RawTelegram.rssi_dbm` is declared `int | None` (returns `None` when the dongle reports
RSSI unknown, i.e., `0xFF`). The existing `burst-300.jsonl` fixture has `rssi_dbm: null`
on every entry — every integration test will produce a `None` RSSI.

The design's `FormattedTelegram.rssi_dbm: int` will cause a mypy strict type error and
no formatter behavior is defined for the `None` case.

**Suggested fix:**
- Type: `rssi_dbm: int | None`
- Display: render as `"RSSI N/A"` in the log line when `None`
- Add unit test `test_format_telegram_rssi_none` asserting the "N/A" output

Applied to design doc: §3.2 type fixed to `int | None`; display fallback added; unit test added.

---

**M4 — Formatter spec references `t.rssi` — attribute does not exist on `RawTelegram`**

§1-B task 6 states: `RSSI: integer dBm from \`t.rssi\``.

`RawTelegram` exposes `rssi_dbm: int | None` as a property, not `rssi`. Accessing `t.rssi`
at runtime raises `AttributeError`. mypy strict would also catch this.

**Suggested fix:** Change `t.rssi` to `t.rssi_dbm` everywhere in the formatter spec.

Applied to design doc: Task 6 corrected to `t.rssi_dbm`.

---

**M5 — No `test_filter_live` in §6 test table**

Round 3 M1 added a live-filtering clause to §3.3:
> "when `filter_id` is set, new incoming `TelegramReceived` messages are also filtered —
> the handler skips non-matching entries without adding them to `_buffer` or `RichLog`."

This is a distinct code path from the retroactive re-render tested by `test_filter_retroactive`.
Without an explicit test, TDD cannot drive this code path and it risks being unimplemented.

**Suggested fix:** Add `test_filter_live` to the integration test table:
Scenario — set filter for ID-A, then replay ID-A and ID-B telegrams; assert only ID-A entries
appear in RichLog and `_buffer`.

Applied to design doc: `test_filter_live` added to §6 integration test table.

---

### SHOULD-FIX

**S1 — `_buffer` cap mechanism not specified**

§3.3 says `_buffer: list[FormattedTelegram]` capped at 10,000 entries, but a `list` in Python
grows unbounded without explicit trimming. No trimming logic is described. In a long-running
session (hours), `_buffer` could far exceed 10,000 entries, making retroactive filter re-render
slow and consuming significant memory.

The `_pause_buffer` correctly uses `deque(maxlen=256)`. The `_buffer` should use the same
pattern for consistency and correctness.

**Suggested fix:** Change `_buffer` to `collections.deque(maxlen=10_000)`. The deque
automatically drops the oldest entry on overflow — same semantics as `_pause_buffer` and
`RichLog(max_lines=10_000)`.

Applied to design doc: §3.3 and §1-B task 5 updated to `deque[FormattedTelegram]`.

---

**S2 — Auto-discovery tests not named in §6 test table**

The §6 coverage note says "Auto-discovery paths (§1-E) must have targeted tests using
mocked serial port scan" but no specific test cases are listed. The auto-discovery logic
has at least 4 distinct paths (0/1/multiple dongles found, and the `asyncio.to_thread`
wrapping itself). Without named tests, TDD cannot drive these paths.

**Suggested fix:** Add a named auto-discovery test table:
- `test_autodiscovery_single_dongle` — 1 match → auto-connect, no modal
- `test_autodiscovery_multiple_dongles` — 2 matches → selection modal shown
- `test_autodiscovery_no_dongle` — 0 matches → FakeDongle modal shown
- `test_autodiscovery_uses_to_thread` — verifies `comports()` called via `asyncio.to_thread`

Applied to design doc: Auto-discovery test table added to §6.

---

**S3 — FilterInput validation for invalid input not specified**

§3.3 describes the happy path (8 hex digits, `0x` prefix accepted) but undefined behavior for:
- Empty Enter (user clears the field and presses Enter)
- Non-hex characters (e.g., `GHIJ1234`)
- Input longer than 8 digits

These cases will reach the filter application code. Without a spec, implementations diverge.

**Suggested fix (recommended behavior):**
- Empty Enter → same as Escape: clear filter, re-render full log
- Non-hex input → show error CSS class on the FilterInput, do not apply filter
- >8 digits → truncate silently to the last 8 hex digits OR show error and reject

Not applied to design doc — this is an implementer decision; add a note to §3.3.

---

**S4 — RORG name lookup source not specified**

Task 6 says "name lookup" for RORG display (`RPS (0xF6)`) but does not specify where the
human-readable names come from. `enocean_async.protocol.erp1.rorg.RORG` is a Python Enum;
`RORG.RPS.name` returns the string `"RPS"`. This is likely sufficient for the MVP, but the
design should confirm it rather than leaving implementers to guess.

For unknown RORG values not in the enum, a fallback is also needed (e.g., `"UNKNOWN (0xXX)"`).

**Suggested fix:** Specify in task 6: use `rorg.name` from the `RORG` enum for known values;
fall back to `f"UNKNOWN (0x{rorg_byte:02X})"` for values outside the enum.

Not applied to design doc — add as a note to §1-B task 6.

---

**S5 — Task 5 (SnifferScreen) is coarse-grained**

Task 5 bundles: screen class creation, RichLog setup, `_buffer` deque, TelegramReceived
handler, formatting dispatch, and filter application into one task. This is 5–6 distinct
implementation units that could each be independently tested.

**Suggested split:**
- 5a: SnifferScreen skeleton — compose layout, RichLog, key bindings, no message handling
- 5b: TelegramReceived handler + `_buffer` management + formatting dispatch
- 5c: Filter application — retroactive re-render + live-path skip

For a solo implementer this is optional. For parallel or TDD-first work, the split
makes each step individually deliverable with a failing test.

Not applied to design doc — noted for implementer discretion.

---

## Findings Summary

| ID | Severity | Category | Applied? |
|----|----------|----------|----------|
| M1 | must-fix | Implicit dependency (fixture) | ✓ Design doc updated |
| M2 | must-fix | Infrastructure (path bug) | ✓ Design doc updated |
| M3 | must-fix | Error handling (RSSI None) | ✓ Design doc updated |
| M4 | must-fix | Error handling (wrong attr name) | ✓ Design doc updated |
| M5 | must-fix | Test coverage (live-filter) | ✓ Design doc updated |
| S1 | should-fix | Error handling (_buffer unbounded) | ✓ Design doc updated |
| S2 | should-fix | Test coverage (autodiscovery) | ✓ Design doc updated |
| S3 | should-fix | Error handling (FilterInput) | ✗ Noted only |
| S4 | should-fix | Implicit dependency (RORG names) | ✗ Noted only |
| S5 | should-fix | Coarse-grained task | ✗ Noted only |

## Actions Applied to Design Doc

- [x] M1: Task 17 updated — fixture exists but lacks 4BS entries; must be fixed before testing
- [x] M2: Task 16 path corrected to three `.parent` hops; importlib.resources approach noted
- [x] M3: §3.2 `rssi_dbm` type changed to `int | None`; display fallback ("N/A") added
- [x] M3: `test_format_telegram_rssi_none` added to §6 unit test table
- [x] M4: Task 6 formatter spec: `t.rssi` → `t.rssi_dbm`
- [x] M5: `test_filter_live` added to §6 integration test table
- [x] S1: §3.3 and task 5 `_buffer` changed from `list` to `deque(maxlen=10_000)`
- [x] S2: Named auto-discovery test table added to §6
- [x] Status line in §1 updated to reflect completeness round 1
