# Integration Analysis

## Summary

Phase 1 (Sniffer MVP) builds directly on the completed Phase 0 foundation. The
integration surface is narrow: nearly all new work is additive UI layering on top
of the already-wired dongle pipeline. The Phase 0 `_telegrams_worker` stub in
`app.py` was deliberately left as `pass` — Phase 1 fills that stub with real
display logic. The only non-additive change is extending `StatusHeader` (rename /
augment) and adding a `base_id` property to the `Dongle` Protocol.

Two structural decisions will shape the rest of the roadmap: (1) whether Phase 1
introduces the `ui/` sub-package now (as the architecture target specifies) or
leaves code in `app.py` temporarily, and (2) how the pause/resume feature interacts
with the dongle queue model already in place.

## Analysis

### Key Considerations

- **Phase 0 is the load-bearing foundation.** `DongleService`, `FakeDongle`,
  `Settings`, and `EnoceanTuiApp` are all present and tested. No Phase 0 API needs
  to be broken to build Phase 1.
- **The `_telegrams_worker` stub is the primary integration seam.** It already
  iterates `dongle.telegrams()` and does nothing — Phase 1 replaces the `pass` with
  a call to a new `TelegramLog` widget.
- **`RawTelegram` already carries every field the sniffer needs:** `received_at`
  (timestamp), `sender` (ID), `rorg` (RORG enum), `payload` (bytes), `rssi_dbm`
  (int | None). No changes to the dongle layer types are required for display.
- **Base ID is the one gap.** The `Dongle` Protocol has no `base_id` property.
  `DongleService` can read it from `Gateway.base_id` after connect; `FakeDongle`
  returns a hard-coded default. This is a small, low-risk addition.
- **Pause/resume semantics.** The dongle layer always reads from hardware (to
  prevent serial buffer overflow). Pause is a UI concern: the `TelegramLog` widget
  keeps a counter of telegrams received while paused and stops appending to the
  visible log. The architecture's backpressure model (bounded asyncio queue, size
  256) is already in place; during pause the queue drains normally into the worker,
  which just skips display.
- **Architecture target layout calls for `ui/` sub-package.** Phase 1 is the
  right moment to introduce `ui/screens/sniffer.py` and `ui/widgets/telegram_log.py`
  as specified in `architecture.md §Module layout`. Doing it now avoids a later
  refactor that would break all imports.

### Options Explored

#### Option 1: Inline everything in `app.py` (quick, deferred structure)

- **Description**: Add Phase 1 UI directly to `app.py` without creating the `ui/`
  sub-package. `TelegramLog` is a class in the same file.
- **Pros**: Smallest diff, zero directory churn.
- **Cons**: Contradicts the established architecture target; creates a refactor
  burden before Phase 2 anyway; makes `app.py` a grab-bag as the project grows.
- **Effort**: Low

#### Option 2: Introduce `ui/` sub-package now (recommended)

- **Description**: Create `src/enocean_async_tui/ui/widgets/telegram_log.py` and
  `src/enocean_async_tui/ui/screens/sniffer.py` as Phase 1 ships. `app.py` remains
  the `App` subclass but composes a `SnifferScreen`.
- **Pros**: Aligns with `architecture.md`; Phase 2 and later slices have clear homes
  for their own screens and widgets; testable in isolation.
- **Cons**: Slightly more files, one extra import layer.
- **Effort**: Low–Medium (a few extra `__init__.py` files, clean imports)

#### Option 3: Single-screen vs. multi-screen App

- **Description**: Option A — Phase 1 is the only screen; the App just composes the
  sniffer widgets directly (no `push_screen`). Option B — the App keeps a default
  screen stack and `SnifferScreen` is pushed on mount.
- **Pros of A**: Simpler for Phase 1 alone.
- **Pros of B**: Phase 2 adds a registry screen alongside the sniffer; screen-stack
  navigation is already the right model.
- **Recommendation**: Use `SnifferScreen` as a `Screen` subclass from the start so
  Phase 2 can push the registry screen alongside it without refactoring Phase 1.
- **Effort**: Low

#### Option 4: Pause by suspending the dongle worker

- **Description**: `p` cancels `_telegrams_worker`; resume restarts it.
- **Pros**: Zero queue accumulation while paused.
- **Cons**: Telegrams arriving during pause are lost (contradicts spec: "without
  dropping"). Worker cancel/restart adds lifecycle complexity.
- **Effort**: Medium, but spec-violating.

#### Option 5: Pause at the widget level (recommended)

- **Description**: `_telegrams_worker` always calls `telegram_log.on_telegram(t)`.
  `TelegramLog` has a `_paused: bool` flag. When paused, it increments a counter
  and skips `RichLog.write`. When resumed, it displays the queued count ("N
  telegrams received while paused") and resumes writing.
- **Pros**: Dongle layer untouched; no telegram loss; matches spec.
- **Cons**: Telegrams received during pause are permanently discarded from the
  visible log (not replayed). This is acceptable for a live sniffer.
- **Effort**: Low

### Recommendation

Use **Option 2** (introduce `ui/` sub-package) with **Option 3B** (`SnifferScreen`
as a `Screen`) and **Option 5** (widget-level pause). This delivers Phase 1 per
spec while laying the correct structural groundwork for Phase 2.

The concrete change set:

1. **`dongle/protocol.py`** — add `base_id: int | None` property to the `Dongle`
   Protocol. `DongleService` reads it from `Gateway.base_id`; `FakeDongle` exposes
   a configurable attribute (default `0x01234567`).

2. **`ui/widgets/telegram_log.py`** — new `TelegramLog(Widget)` wrapping
   `RichLog`. Public API:
   - `on_telegram(t: RawTelegram) -> None` — writes one formatted line
   - `action_clear() -> None` — clears the log
   - `action_toggle_pause() -> None` — toggles pause; shows counter banner
   - `set_filter(sender_id: int | None) -> None` — hides non-matching lines

3. **`ui/screens/sniffer.py`** — new `SnifferScreen(Screen)`. Composes
   `StatusHeader` (extended to show port + base_id), `TelegramLog`, `Footer`.
   Bindings: `q` quit, `c` clear, `p` pause, `f` filter.

4. **`app.py`** — replace `Label("Phase 0 — placeholder")` with `SnifferScreen`
   composition (or push it on mount). Forward `_telegrams_worker` output to
   `TelegramLog.on_telegram`. Remove the `pass` stub.

5. **`settings.py`** — no changes required. Port is already in `Settings.port`
   and is available for the header.

## Constraints Identified

- **Python 3.14 + Textual ≥ 8.2.3.** `RichLog` is stable in this range.
  The `Pilot` test API used in `tests/test_app.py` is the standard approach;
  no compatibility concerns for Phase 1.
- **Single asyncio loop.** All worker tasks and UI updates share one loop.
  `TelegramLog.on_telegram` must not block; `RichLog.write` is non-blocking
  in Textual's model.
- **Coverage gate at 80 %.** Phase 1 adds new code; new Pilot tests must keep
  the gate green. The sniffer screen and telegram log widget need test coverage.
- **`Gateway.base_id`** availability must be verified in the `enocean-async`
  ≥ 0.13.1 API before adding the Protocol property. If `Gateway` exposes it
  only after `start()` completes, the header must handle a `None` state during
  connect/reconnect.
- **Filter UX.** The spec says "filter by sender ID" but does not specify the
  interaction. A simple text-input modal is the most usable approach (avoids
  hard-to-type hex IDs from the keyboard). This is a mild scope question for
  the UX analysis dimension.

## Open Questions

1. **Does `enocean_async.Gateway` expose `base_id`?** If yes, what type and when
   is it populated? If not, should the header omit the base ID or show a static
   placeholder?
2. **Filter interaction model.** Does `f` open an inline text input bar (like
   a terminal search bar) or a modal? The UX dimension should decide; the
   integration just needs a `set_filter(int | None)` API on `TelegramLog`.
3. **Paused-telegram fate.** Spec says "without dropping telegrams (queue while
   paused)". Should we replay them on resume, or just show the count? Replaying
   a burst of 300+ telegrams on resume could be jarring. Recommendation: show
   count, discard from view (hardware buffer still intact for the stream).
4. **`SnifferScreen` vs inline compose.** Confirmed by synthesis: use a `Screen`
   subclass so Phase 2 can add a second screen without touching Phase 1 code.

## Integration Points

- **UX Analysis**: Owns the filter interaction model and the pause/resume UX
  details (counter banner wording, filter input placement). `TelegramLog` API is
  designed to accept whatever the UX dimension decides.
- **API & Interface Design**: May identify additional dongle API extensions (e.g.,
  base_id type, whether `send()` is used in Phase 1 — it is not). No conflicts
  expected.
- **Data Model Design**: Phase 1 has no persistence — all state is ephemeral. The
  `Store` Protocol is not touched. Data dimension work begins in Phase 2
  (device registry).
- **Security Analysis**: Serial port access is the only privileged resource;
  already mediated by `DongleService`. No new attack surface in Phase 1.
- **Scalability Analysis**: The 256-entry bounded queue and overflow warning system
  are already in place. Phase 1 doesn't stress this path beyond what Phase 0
  already tested.
