# Scalability Analysis

## Summary

Phase 1 Sniffer MVP is bounded in scale by two physical constraints that no software
optimization can remove: the EnOcean protocol duty cycle (~120 telegrams/second ceiling
on a single 868 MHz channel) and the single-dongle, local-only architecture. Within
those limits the hot path is O(1) per telegram with a bounded ~4–6 MB memory footprint
regardless of session duration.

The one structural risk is the O(n) display-buffer eviction (`list.pop(0)`) and the
O(n) filter re-render over up to 10,000 entries. Both are acceptable at realistic
EnOcean rates (1–50 telegrams/second) and are self-limiting by design, but a trivial
swap from `list` to `deque(maxlen=10_000)` eliminates the eviction cost for free.
No other Phase 1 path warrants optimization.

## Analysis

### Key Considerations

- **Protocol ceiling is the dominant constraint.** EnOcean 868 MHz ISM operates under
  a 1% duty cycle rule. A single telegram occupies roughly 8–50 ms on-air, giving a
  hard ceiling of ~20–120 telegrams/second per channel. Real deployments (home, small
  building) produce 1–20 telegrams/second aggregate. The "1000x scale" question is
  physically unreachable on one dongle.
- **Data path is O(1) per telegram end-to-end.** `DongleService.telegrams()` yields
  one `RawTelegram` → `format_telegram()` runs in ~5–10 µs (one `datetime.now()` call
  plus string formatting) → `app.post_message()` enqueues a lightweight message →
  `RichLog.write_markup()` appends one line. No off-loop I/O, no locks.
- **All in-memory state is bounded.** Display buffer: 10,000 `FormattedTelegram`
  entries (~4–6 MB). Pause buffer: 256 entries (~100–150 KB). Filter state: a single
  `int | None`. No growth is unbounded.
- **The only O(n) operation in normal use is filter re-render.** Clear → iterate
  10,000 entries → re-append matching lines to `RichLog`. Triggered only on Enter.
- **Display-buffer eviction is `list.pop(0)` — O(n) at steady state.** Once the 10,000
  cap is reached every new telegram evicts the oldest. At 50 telegrams/second this is
  50 O(n) pops/second on a 10,000-element list: ~5 µs per pop in CPython, so ~250 µs/s
  overhead. Negligible today, trivially eliminated by using `deque(maxlen=10_000)`.
- **Single asyncio event loop means no concurrency overhead.** Worker, message dispatch,
  and Textual render all run on one thread. There are no locks, no thread-safe queues,
  no context switches between the dongle reader and the UI.

### Options Explored

#### Option 1: Unbounded display buffer

- **Description**: Remove the 10,000-entry cap; buffer all telegrams received in the
  session.
- **Pros**: No data loss; retroactive filter always operates on the full session history.
- **Cons**: At 10 telegrams/second, a 4-hour session accumulates 144,000 entries
  (~60–90 MB). Filter re-render becomes seconds-long. `RichLog` itself has `max_lines`;
  entries beyond that are invisible anyway. Memory grows unboundedly.
- **Effort**: Low (delete the truncation logic) — but the outcome is wrong.

#### Option 2: Fixed cap at 10,000 entries — plain `list` (current design)

- **Description**: `_buffer: list[FormattedTelegram]` with `pop(0)` when full.
- **Pros**: Simple; buffer and `RichLog` stay in sync without extra tracking.
- **Cons**: O(n) eviction cost at steady state once buffer is full. At realistic rates
  this is immeasurable; at theoretical protocol ceiling (~120/s) it becomes ~600 µs/s
  of overhead.
- **Effort**: Already designed.

#### Option 3: Fixed cap at 10,000 entries — `deque(maxlen=10_000)` (recommended)

- **Description**: Replace `list` with `collections.deque(maxlen=10_000)`. Oldest
  entry is automatically dropped when the deque is full — O(1) amortized.
- **Pros**: O(1) append + eviction; same memory; mirrors how `_pause_buffer` already
  works. Filter re-render iterates the deque in O(n) — unchanged.
- **Cons**: `deque` does not support `O(1)` random access by index (only `O(n)`).
  For filter re-render (a linear scan, not random access) this is immaterial.
- **Effort**: One-line change: `list[FormattedTelegram]` → `deque[FormattedTelegram](maxlen=10_000)`.

#### Option 4: Batch `RichLog` writes during filter re-render

- **Description**: Wrap the re-render loop in Textual's `with self.app.batch_update():`
  context manager to defer DOM reflow until all lines are appended.
- **Pros**: Reduces filter re-render latency significantly — Textual redraws once after
  the batch instead of after each `write_markup()` call.
- **Cons**: Requires understanding Textual's `batch_update` contract; adds a small code
  change. Not required unless filter latency proves unacceptable in practice.
- **Effort**: Low — a two-line wrapper around the existing loop.

#### Option 5: Rate-limit `TelegramReceived` messages (message coalescing)

- **Description**: Coalesce multiple `TelegramReceived` messages within a single Textual
  render frame (≤16 ms at 60 fps) into a single batch write.
- **Pros**: Reduces per-frame message dispatch overhead at high telegram rates.
- **Cons**: Adds complexity; unnecessary at all realistic EnOcean rates. Textual already
  batches renders within a frame — multiple messages enqueued before the next frame are
  handled in sequence without intermediate redraws.
- **Effort**: Medium — not warranted for Phase 1.

### Recommendation

**Option 3** (`deque(maxlen=10_000)`) for the display buffer. It is a one-line change
that eliminates the only structural inefficiency (O(n) eviction) without adding any
complexity or changing behavior.

**Option 4** (batch `RichLog` writes) should be held in reserve — implement only if
filter re-render latency is perceptible in practice. For 10,000 entries at 60 fps,
Textual typically processes this in under 500 ms; whether that is acceptable depends on
use patterns.

**Options 1, 2, 5** should not be pursued in Phase 1.

## Constraints Identified

- **Protocol ceiling (hardware):** ~120 telegrams/second maximum on a single 868 MHz
  EnOcean channel. This is a physical constraint, not a soft limit. "1000x scale" is
  not achievable on one dongle.
- **Memory budget:** 10,000 `FormattedTelegram` objects with `__slots__` plus `RawTelegram`
  back-references sum to ~4–6 MB at cap. The `RichLog` widget holds its own render buffer
  (~1–2 MB additional for markup). Total session memory is bounded at ~8–10 MB.
- **O(n) filter re-render is unavoidable at the Phase 1 scale ceiling.** With 10,000
  entries and no index, any filter requires a full scan. At the given cap, this is
  acceptable. Phase 3+ (decoding, registry) may need an indexed structure.
- **Single event loop precludes parallel rendering.** The `RichLog` re-render during
  filter application blocks the Textual event loop. At 10,000 entries this is a brief
  stall, not a deadlock. There is no way to run it in a background thread without
  decoupling `RichLog` writes from the asyncio loop (a much larger change).
- **`list.pop(0)` O(n) eviction** (see Option 3 above) — a constraint to address before
  first production use, not a blocker.
- **Auto-discovery startup cost:** `serial.tools.list_ports.comports()` runs once in
  `asyncio.to_thread` at startup. On systems with many USB devices or slow kernel USB
  enumeration this can take 1–2 seconds. No timeout is specified; the app appears to
  hang until discovery completes. Not a recurring scalability concern, but a startup
  latency one.

## Open Questions

1. **Textual `batch_update` semantics for `RichLog`.** Does wrapping filter re-render
   in `batch_update` actually defer `RichLog`'s internal layout recomputation, or does
   `RichLog.write_markup` maintain its own internal buffer? Needs a quick Textual source
   read or empirical test before Option 4 is implemented.
2. **`deque` iteration order during filter re-render.** A `deque` iterates in insertion
   order (oldest to newest) — identical to `list`. Confirm iteration order is preserved
   when converting to `deque(maxlen=10_000)` so the filter re-render produces entries
   in chronological order.
3. **Auto-discovery timeout.** Should `asyncio.to_thread(comports)` be wrapped with
   `asyncio.wait_for(…, timeout=5.0)` to bound startup latency on pathological systems?
   Relevant if the TUI is ever run in embedded or CI environments with unusual USB stacks.
4. **`_pause_buffer` deque already O(1).** Confirm that `deque(maxlen=256).append()` is
   indeed O(1) amortized in CPython — it is — and that no second-guessing of this is
   needed.

## Integration Points

- **Data Model (data.md):** The recommendation in data.md to use `deque(maxlen=10_000)`
  instead of `list` for future phases aligns exactly with Option 3 above — this analysis
  recommends making that change in Phase 1, not deferring it. The `FormattedTelegram`
  shape (frozen, slots, `sender_int: int` for O(1) filter comparison, precomputed
  `line: str`) is already optimised for the filter-re-render hot path.
- **Integration (integration.md):** The integration analysis confirms the pause buffer
  (deque 256) and overflow warning are already in place. This analysis adds the
  recommendation to also use `deque` for the display buffer, for consistency.
- **Architecture/Implementation:** The `SnifferWorker` hot path described in design-doc.md
  (post_message → on_telegram_received → RichLog.write_markup) is O(1) per telegram and
  non-blocking throughout. No changes to the worker are required for scalability.
- **Phase 2 (device registry):** Sender IDs accumulate over a session in `_buffer`. With
  `sender_int: int` already stored, Phase 2 can scan the buffer for unique sender IDs in
  O(n) without re-parsing. If Phase 2 introduces a real-time registry update on every
  telegram, that adds an O(log n) insert per message — still well within budget at
  EnOcean rates.

---

## Scale Projection Summary

| Dimension | Baseline (1–5 /s) | 10x (10–50 /s) | 100x (≈120/s max) | 1000x |
|-----------|------------------|----------------|-------------------|-------|
| Protocol feasibility | Yes | Yes | At physical ceiling | Impossible (hardware) |
| Buffer fills in | 33–165 min | 3–17 min | ~83 s | — |
| Memory at steady state | ~0.5–1 MB | ~2–4 MB | ~5–6 MB | — |
| Hot-path cost/telegram | ~10 µs | ~10 µs | ~10 µs | — |
| Eviction cost (list) | ~0 µs | ~1–5 µs | ~5 µs | — |
| Filter re-render | ~50–100 ms | ~200–500 ms | ~500 ms–1 s | — |
| Verdict | Green | Green | Green (near protocol limit) | N/A |

The 1000x row is not a target — it is physically impossible on one EnOcean dongle.
The software bottleneck (filter re-render) is bounded by the 10,000-entry cap and is
never reached at practical scale until the user explicitly triggers a filter. All other
paths are O(1) per telegram and safe for indefinite session duration.
