# Data Model Design

## Summary

Phase 1 (Sniffer MVP) is entirely ephemeral — no data survives a session restart.
All state lives in Python objects held by the running `SnifferScreen` and its worker.
The raw dongle layer already provides `RawTelegram` (frozen dataclass, all needed
fields). Phase 1 adds one derived type (`FormattedTelegram`) and two bounded
in-memory buffers. No storage backend, schema migrations, or persistence plumbing
are introduced in Phase 1; that work begins in Phase 2 (device registry).

The data model is therefore a "display pipeline" design: `RawTelegram` is produced
by the dongle layer, projected into `FormattedTelegram` by a pure formatter, held
in a bounded list for retroactive filtering, and rendered into a `RichLog` widget.
The only structural decision with lasting impact is how `FormattedTelegram` is
defined — its shape determines the formatter API, the filter contract, and what
Phase 2 can persist without breaking callers.

## Analysis

### Key Considerations

- `RawTelegram` already carries every field the sniffer needs: `received_at`
  (datetime), `sender` (EURID | BaseAddress), `rorg` (RORG enum), `payload`
  (bytes), `rssi_dbm` (int | None). No dongle layer changes are required for display.
- `FormattedTelegram` is a derived, display-oriented projection of `RawTelegram`. It
  should be a frozen dataclass: all fields are strings/ints computed once, never
  mutated, and cheap to hold in a list of 10 000.
- The display buffer (`list[FormattedTelegram]`, cap 10 000) exists solely for
  retroactive filter re-renders. It is the only "store" in Phase 1.
- The pause buffer (`deque[FormattedTelegram](maxlen=256)`) is a ring buffer — not
  a store. It accumulates telegrams during pause and drains on resume.
- Filter state is a single `int | None` (the parsed sender ID). This is not persisted.
- No schema evolution is needed in Phase 1. All state is reconstructed from the live
  hardware stream on each run.
- Phase 2 will introduce a device registry. The `RawTelegram.sender` field (EURID)
  is the natural registry key. `FormattedTelegram` should carry `sender_int: int` as
  a pre-parsed integer for O(1) filter comparisons and as a future FK candidate.

### Options Explored

#### Option 1: Store `RawTelegram` in the display buffer

- **Description**: Keep `_buffer: list[RawTelegram]`; format on demand during filter
  re-renders.
- **Pros**: Minimal duplication; raw data available for future use without re-fetching.
- **Cons**: Re-formatting 10 000 entries on every filter keypress (even on Enter) is
  wasteful; the formatter is pure but not free. More importantly, `RawTelegram.sender`
  is `EURID | BaseAddress` — not directly comparable to a hex string the user types.
  Filter logic would need to re-parse types on every comparison.
- **Effort**: Low

#### Option 2: Store `FormattedTelegram` in the display buffer (Recommended)

- **Description**: Format once on receipt; store `FormattedTelegram` in
  `_buffer: list[FormattedTelegram]`. Filter re-render iterates the buffer comparing
  `entry.sender_int` against the filter value.
- **Pros**: Format cost is O(1) per telegram at receive time. Filter re-render is a
  tight integer comparison loop over pre-formatted strings — fast for 10 000 entries.
  Display string (`line`) is precomputed. `sender_int` is unambiguous (already parsed,
  no string conversions in the hot path).
- **Cons**: Doubles memory vs raw-only approach (raw + formatted). At 10 000 entries
  with ~200 bytes per `FormattedTelegram`, that is ~2 MB peak — well within budget.
- **Effort**: Low

#### Option 3: Store both raw and formatted, lazily formatted

- **Description**: `_buffer: list[tuple[RawTelegram, FormattedTelegram | None]]`;
  format lazily when first displayed.
- **Pros**: Defers format cost until needed.
- **Cons**: Adds complexity for no real benefit in a live sniffer where every telegram
  is displayed immediately. The lazy path is never hit in normal use.
- **Effort**: Medium

#### Option 4: Persist telegrams to SQLite between sessions

- **Description**: Write each `RawTelegram` to a local SQLite file on receipt.
- **Pros**: Survives session restart; enables cross-session analysis.
- **Cons**: Out of scope for Phase 1; introduces synchronous I/O on the event-loop
  hot path unless carefully wrapped; schema design needed before Phase 2 requirements
  are known. Premature.
- **Effort**: High (+ risk of over-design)

#### Option 5: JSON/JSONL file log (rolling)

- **Description**: Append-only JSONL file, one telegram per line.
- **Pros**: Human-readable; grep-able; trivial to implement.
- **Cons**: Same out-of-scope issue as Option 4; no query capability; schema
  discipline required from day one. Phase 2 will want indexed queries by sender ID,
  timestamp range — JSONL doesn't support that without full-scan.
- **Effort**: Medium

### Recommendation

Use **Option 2**: a frozen `FormattedTelegram` dataclass stored in
`list[FormattedTelegram]`. Carry `sender_int: int` explicitly as a pre-parsed integer
for filter comparisons. Keep a back-reference to `RawTelegram` (`raw` field) in case
Phase 2 needs additional fields without re-processing.

**Proposed `FormattedTelegram` shape:**

```python
@dataclass(frozen=True, slots=True)
class FormattedTelegram:
    timestamp: str      # "2026-05-07T14:23:01.042" — ISO 8601 with ms
    sender_id: str      # "0xABCD1234" — display string
    sender_int: int     # 0xABCD1234 — integer for O(1) filter comparisons
    rorg_name: str      # "RPS (0xF6)" — display string
    payload_hex: str    # "F600..." — full payload hex, uppercase, no 0x prefix
    rssi_dbm: int | None  # -62 or None if unknown
    line: str           # precomputed full log line for RichLog (avoids f-string on re-render)
    raw: RawTelegram    # back-reference, not displayed
```

The `line` field trades ~100 bytes per entry for zero formatting cost during filter
re-renders. At 10 000 entries that is < 1 MB.

**Buffer sizing:**

| Buffer | Type | Cap | Rationale |
|--------|------|-----|-----------|
| `_buffer` | `list[FormattedTelegram]` | 10 000 | Matches `RichLog(max_lines=10_000)`. Truncate oldest when full (pop from front). |
| `_pause_buffer` | `deque[FormattedTelegram]` | 256 | Ring-buffer: oldest dropped silently; `_dropped_count` tracks overflow. Matches hardware queue depth. |

**Filter contract:**

```python
filter_id: int | None  # None = no filter; int = parsed sender ID
```

Matching: `entry.sender_int == filter_id`. Applied during re-render only (not on
every received telegram). Active filter is cleared to `None` on `Escape`.

## Constraints Identified

- **No blocking I/O on the event loop.** `FormattedTelegram` construction must be
  synchronous and non-blocking. `datetime.now()` and string formatting qualify.
- **`rssi_dbm` is `int | None`.** `RawTelegram.rssi_dbm` returns `None` when RSSI
  is unknown (raw value `0xFF`). Display as `"N/A"` or `"–"` rather than crashing.
  The log line format spec says `RSSI -62 dBm` — for None, show `RSSI – dBm`.
- **`RawTelegram.sender` type is `EURID | BaseAddress`.** The formatter must handle
  both: `EURID` has an integer representation (`.address` or `int()` cast);
  `BaseAddress` represents the base station (sender == 0x00000000 range). Parse
  to `int` for `sender_int`. Use `str(sender)` or hex formatting for `sender_id`.
- **`payload` vs `telegram_data`.** `RawTelegram.payload` is `raw.telegram_data` —
  this is the ERP1 telegram data bytes. Ensure this is the full payload (including
  data bytes but not ESP3 framing) before hex-encoding. Verify against the PRD
  format spec.
- **List truncation cost.** `list.pop(0)` on a 10 000-entry list is O(n). If the
  sniffer runs for hours at high telegram rates, this cost accumulates. At realistic
  EnOcean rates (< 100 telegrams/s burst), this is negligible. If future phases
  target higher rates, replace with a `collections.deque(maxlen=10_000)` and
  re-render from the deque. For Phase 1, a plain list is correct and simple.

## Open Questions

1. **`RawTelegram.sender` integer extraction.** What is the correct way to extract
   an `int` from `EURID | BaseAddress`? Is `int(sender)` defined for both types?
   If not, the formatter needs a conditional or a helper. This should be verified
   against the `enocean-async` ≥ 0.13.1 API before the formatter is written.
   (Low risk — likely `int(eurid)` works; BaseAddress is likely `0`.)
2. **`payload` completeness.** `RawTelegram.payload` maps to `raw.telegram_data`.
   Confirm this is the full ERP1 data field (user bytes) as the PRD specifies, not
   just the application data after stripping the RORG byte. The hex encoding must
   match exactly what a hardware sniffer would show.
3. **Display buffer eviction policy.** When `_buffer` reaches 10 000 entries, should
   new entries evict oldest (ring), or stop buffering (stop-at-cap)? The `RichLog`
   `max_lines` setting handles the visible log; the buffer exists only for filter
   re-renders. Recommendation: mirror `max_lines` exactly — drop oldest from `_buffer`
   when a new entry is added at cap, keeping buffer and display in sync.
4. **Phase 2 persistence format.** Phase 2 introduces a device registry. The obvious
   key is `sender_int` (EURID as integer). Should `FormattedTelegram` store the raw
   `RawTelegram.received_at: datetime` as well as the formatted `timestamp: str`? A
   datetime is more useful for Phase 2 queries than a string. Recommendation: yes —
   add `received_at: datetime` to `FormattedTelegram` alongside `timestamp: str`.

## Integration Points

- **Architecture/Implementation (rust polecat):** Owns `SnifferWorker` and the
  `_buffer` / `_pause_buffer` lifecycle. The `FormattedTelegram` dataclass should
  live in `src/enocean_async_tui/ui/formatters.py` (or `ui/types.py`), not in
  `dongle/types.py` — it is a display concern, not a dongle concern.
- **UX Analysis:** Owns the exact log line format string and the filter input UX.
  The `line: str` field in `FormattedTelegram` should match exactly what the UX
  dimension specifies (spacing, separators, field order). If the format spec changes,
  only the formatter changes — not the buffer or filter logic.
- **Integration Analysis (chrome polecat):** Confirmed Phase 1 is persistence-free.
  The `Store` Protocol is not touched. This analysis is consistent with that decision.
- **Phase 2 (future):** The `sender_int: int` field is the natural FK for a device
  registry table. `received_at: datetime` (recommended addition in OQ4) would enable
  time-range queries. No schema changes are required to Phase 1 code to support this —
  Phase 2 adds a new storage layer that reads from the existing types.
