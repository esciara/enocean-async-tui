# PRD Alignment Round 3: User Stories + Open Questions
## Phase 1 Sniffer MVP

**PRD:** `.prd-reviews/sniffer-mvp/prd-draft.md`
**Plan:** `.designs/sniffer-mvp/design-doc.md`
**Reviewer:** rust (combined A + B — sling unavailable to polecats)
**Date:** 2026-05-07
**Based on:** Round 2 changes applied by rust (eat-wfs-ayqsk)

---

## Part A — User Stories Coverage

PRD defines 4 scenarios. Each is traced end-to-end through the plan.

### Scenario A — Debug a broken automation

Alice runs `enocean-tui`, watches the live log, presses `f`, enters a sender ID,
and confirms the filter shows only that device.

| Step | Plan Coverage | Status |
|------|---------------|--------|
| Run `enocean-tui` → connect to dongle | §4.2 auto-discovery; §3.1 SnifferWorker starts on mount | COVERED |
| Live scrolling log appears | §3.1 TelegramReceived → RichLog.write_markup(); §2 Goal 1 | COVERED |
| Press `f`, enter sender ID `ABCD1234` | §5 task 10: `f` binding shows FilterInput; accepts bare hex | COVERED |
| Filter applied on Enter | §3.3: applied on Enter; pending visual state while typing | COVERED |
| Log shows only matching telegrams (retroactive) | §3.3: re-renders from `_buffer` on Enter | COVERED |
| New telegrams from that ID appear after filtering | §3.3 (post-fix): `TelegramReceived` handler skips non-matching entries | COVERED |
| Problem confirmed (switch sends telegram) | Standard display; no extra plan task needed | COVERED |

**Verdict: COVERED** (M1 fix applied — live filtering now explicit in §3.3)

---

### Scenario B — Identify an unknown device

Bob opens `enocean-tui` and watches sender IDs accumulate as he moves through rooms.

| Step | Plan Coverage | Status |
|------|---------------|--------|
| Run `enocean-tui` → connect | §4.2 auto-discovery | COVERED |
| Live log fills with telegrams from multiple sender IDs | §3.1, §3.2 FormattedTelegram with `0x`-prefixed IDs | COVERED |
| Copy IDs from terminal | Standard terminal capability — no plan task needed | COVERED |

**Verdict: COVERED**

---

### Scenario C — Demo without hardware

Carol runs `enocean-tui` without `--port`; app shows FakeDongle modal; she accepts;
sniffer shows replayed telegrams immediately.

| Step | Plan Coverage | Status |
|------|---------------|--------|
| Run without `--port` → auto-discover → none found | §1-E tasks 13-16; §4.2 | COVERED |
| "No dongle" modal → user accepts FakeDongle | §1-E task 16 (existing Phase 0 flow) | COVERED |
| Sniffer shows replayed telegrams from demo recording | §1-E task 16 (post-fix): FakeDongle initialised with `burst-300.jsonl`, `realtime=True` | COVERED |
| Demo recording fixture exists | §1-E task 17 (post-fix): create `tests/fixtures/recordings/burst-300.jsonl` | COVERED |

**Verdict: COVERED** (previous session applied FakeDongle recording fix; S1 adds fixture creation task 17)

---

### Scenario D — Pause and inspect

Dave presses `p` to freeze the log, reads entries, then presses `p` again to resume.

| Step | Plan Coverage | Status |
|------|---------------|--------|
| Press `p` → log freezes (no new entries displayed) | §3.4 `_paused = True`; §5 task 9 | COVERED |
| PAUSED banner shows queued count | §5 task 9 (post-fix): banner reads "PAUSED — N queued" | COVERED |
| Telegrams queue in buffer while paused | §3.4 `_pause_buffer: deque(maxlen=256)` | COVERED |
| Press `p` again → queued telegrams flush to log | §3.4 "flush `_pause_buffer` to `_buffer` and RichLog in order" | COVERED |
| No telegrams dropped (within 256-entry bound) | §3.4, §2 Goal 4 (Q1 clarification: bounded deque, ring-buffer semantics) | COVERED |

**Verdict: COVERED**

---

## Part B — Open Questions Resolution

PRD defines 7 open questions plus 8 clarifications from human review.

### Original Open Questions

| OQ | Question | Plan Resolution | Status |
|----|----------|-----------------|--------|
| OQ1 | Log retention limit | §3 RichLog(max_lines=10_000); §3.3 `_buffer` capped at 10,000 entries | RESOLVED |
| OQ2 | Base ID retrieval (Phase 1 vs Phase 2) | §7: `–` throughout Phase 1; retrieved in Phase 2. §2 Goal 3 annotated. | RESOLVED |
| OQ3 | RSSI display (dBm vs icons) | §7: raw dBm only. §3.2: `rssi_dbm: int` | RESOLVED |
| OQ4 | Pause UX (banner vs header vs footer colour) | §7: Banner "PAUSED — N queued"; §5 task 9 specifies `Static`/`Label` widget | RESOLVED |
| OQ5 | Filter scope (single vs multi sender ID) | §7: single ID, 8 hex digits, `0x` prefix accepted. §3.3 filter model. | RESOLVED |
| OQ6 | RORG display (name vs hex vs both) | §7: name + hex `RPS (0xF6)`. §3.2 rorg_name field. | RESOLVED |
| OQ7 | Log line format and column order | §7 and §2 Goal 2: `YYYY-MM-DDTHH:MM:SS.mmm  0xABCD1234  RPS (0xF6)  <hex>  RSSI -62 dBm` | RESOLVED |

### PRD Clarifications from Human Review

| Q# | Clarification | Plan Reflection | Status |
|----|---------------|-----------------|--------|
| Q1 | Pause buffer = bounded deque 256, ring-buffer semantics, "N dropped" counter | §3.1 docstring, §3.4, §5 task 9 | REFLECTED |
| Q2 | `c` while paused clears log + buffer | §3.4 "Clear while paused" bullet | REFLECTED |
| Q3 | Filter retroactive from in-memory buffer | §3.3 retroactive re-render from `_buffer` | REFLECTED |
| Q4 | Filter applies on Enter, pending visual state | §3.3 "applied on Enter"; §5 task 10 CSS pending class | REFLECTED |
| Q5 | Exact log line format with ISO 8601 ts, `0x` prefix | §3.2 FormattedTelegram, §2 Goal 2 | REFLECTED |
| Q6 | Port not found → auto-discover, then FakeDongle modal | §4.2, §1-E tasks 13-16 | REFLECTED |
| Q7 | 100 ms = display latency not cold-start | §2 Goal 1 note | REFLECTED |
| Q8 | Base ID deferred → shows `–` in Phase 1 | §2 Goal 3 note, §7 | REFLECTED |

---

## Findings Summary

### MUST-FIX

**M1 — Filter live-path not explicit in §3.3 (Scenario A gap)**

§3.3 described retroactive re-render on Enter but was silent on new incoming telegrams
when a filter is already active. Without this, an implementer might allow all new
telegrams through regardless of filter state, breaking Scenario A.

**Fix applied:** Added to §3.3: "when `filter_id` is set, new incoming `TelegramReceived`
messages are also filtered — the handler skips non-matching entries without adding them
to `_buffer` or `RichLog`."

---

### SHOULD-FIX

**S1 — Demo recording fixture not listed as an implementation task (Scenario C gap)**

Task 16 referenced `tests/fixtures/recordings/burst-300.jsonl` but no task created
the fixture. Without it, Scenario C silently breaks at runtime.

**Fix applied:** Added §1-E task 17 specifying creation of `burst-300.jsonl` with
coverage of ≥2 sender IDs and ≥2 RORG types.

---

## Actions Applied to Design Doc

- [x] M1: Added live-filtering clause to §3.3 filter model
- [x] S1: Added §1-E task 17 — create `tests/fixtures/recordings/burst-300.jsonl`
- [x] Updated §1 status line to reflect round 3 review (applied by prior session)
- [x] §3.4 overflow wording tightened (applied by prior session)
- [x] §5 task 9: pause banner detail added (applied by prior session)
- [x] §5 task 10: filter pending-state detail added (applied by prior session)
- [x] §1-E task 16: FakeDongle recording initialisation added (applied by prior session)
