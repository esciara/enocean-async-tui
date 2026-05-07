# User Experience Analysis

## Summary

Phase 1 Sniffer MVP targets developers, makers, and system integrators who already
understand CLI tools and packet-level inspection. The correct mental model is
`tcpdump`-for-EnOcean: run one command, get a live stream, press keys to filter
and inspect. This audience tolerates raw hex output, ISO timestamps, and keyboard-
driven interaction — they do not need graphical affordances.

The design is well-suited to this audience in its core flow. The critical UX risk
is the **filter entry interaction**: requiring an exact 8-digit hex sender ID without
visual feedback creates a friction point that breaks Scenario A (the primary debugging
scenario). Secondary risks are the **silent FakeDongle mode** (users may not realise
they are watching demo traffic) and **auto-discovery startup opacity** (no indication
the app is scanning). Both are straightforward to address in Phase 1.

---

## Analysis

### Key Considerations

- **tcpdump is the right reference point.** Target users have run `tcpdump`, `tshark`,
  or similar tools. They expect: one command to start, immediate output, keyboard
  shortcuts, no configuration wizard. Any deviation from this pattern increases
  perceived complexity without adding value.
- **Workflow is short-session diagnostic, not long-running daemon.** Users run the
  sniffer for 30 seconds to 5 minutes while pressing buttons, walking through rooms, or
  triggering events. The tool must be immediately productive and easy to exit.
- **The log line is the primary UX surface.** Everything else (header, footer, filter
  input) is secondary. The log line format must be readable at a glance under time
  pressure.
- **Filter is the highest-friction interaction.** A sender ID is 8 hex digits. Users
  will need to copy it from a scrolling log and re-type it (or rely on terminal
  copy-paste). Any ambiguity in the expected format (with/without `0x` prefix, case
  sensitivity, partial matching) will cause failures.
- **Pause semantics are counter-intuitive.** Users expect "pause" to mean "freeze —
  nothing is lost." The actual semantics (buffer 256, drop oldest) must be communicated
  clearly and proactively, not only when overflow actually occurs.
- **FakeDongle mode must be visually distinct.** A user doing a demo or test should
  never mistake simulated traffic for real hardware traffic.

---

### Options Explored

#### Option 1: Inline filter bar (current design — recommended)

- **Description**: Pressing `f` reveals an `Input` widget anchored at the bottom of
  the log pane. Placeholder text shows expected format. Filter applies on Enter.
  Escape clears filter and hides the input. While the input is focused, a "pending"
  CSS class dims or italicises the log to signal the filter has not yet applied.
- **Pros**: Consistent with terminal UX conventions (like `/` search in `less` or
  `vim`). No context switch — user stays in the main view. ESC is a universally
  understood "cancel" key.
- **Cons**: Inline input occupies one log line of vertical space while open. If the
  log is scrolling rapidly, opening the filter can be disorienting — the pending state
  must freeze the log (or make clear that live telegrams are still arriving).
- **Effort**: Low — already in the design.

**Recommended enhancements for this option:**
  - Placeholder text: `"Enter sender ID (e.g. ABCD1234 or 0xABCD1234)"` — eliminates
    format ambiguity without a modal.
  - While filter input is open and no Enter yet pressed, continue showing live
    telegrams with a visual dim/italic effect to indicate "pending". This keeps the
    user oriented during high-traffic sessions.
  - After Enter: if the filter matches zero entries in `_buffer`, show a
    `"NO MATCHES — press Escape to clear filter"` notice inline (not a separate widget —
    just an empty `RichLog` with a centred static message). Without this, an empty log
    after filtering looks identical to a disconnected dongle.
  - Filter active indicator: show `"[FILTER: 0xABCD1234]"` in the header or a
    dedicated status line so the user always knows a filter is applied, even when
    scrolling away from the input area.

#### Option 2: Modal dialog for filter entry

- **Description**: Pressing `f` opens a modal overlay with a labelled text input and
  OK / Cancel buttons.
- **Pros**: Unambiguous — the user is clearly in "filter mode". Can include richer
  help text.
- **Cons**: Breaks keyboard flow. Requires mouse or Tab navigation for OK/Cancel.
  Hides the log during entry, removing the reference the user needs to copy the ID.
  Over-engineered for a single-field input in a developer tool.
- **Effort**: Low–Medium.

**Not recommended for Phase 1.** The inline bar (Option 1) matches terminal conventions
and keeps the log visible for reference during entry.

#### Option 3: Real-time (keystroke) filtering

- **Description**: Filter applies live on every keystroke rather than on Enter.
  Log re-renders after each character.
- **Pros**: Immediate feedback; user can see matches narrow as they type.
- **Cons**: Re-rendering 10,000 entries on every keystroke is expensive (see scale.md).
  The filter target is an exact 8-digit hex ID, not a fuzzy string — intermediate
  states (3 or 5 digits typed) produce arbitrary and confusing matches. The PRD
  clarification (Q4) explicitly ruled this out.
- **Effort**: Low (one-line change) but semantically wrong.

**Not recommended.** The Enter-to-apply decision is correct.

#### Option 4: PAUSED banner with explicit telegram-loss warning

- **Description**: When pause buffer overflows (> 256 entries while paused), the
  banner text changes from `"PAUSED — 256 queued"` to
  `"PAUSED — 256 queued · 12 DROPPED"` with the dropped count highlighted in a
  warning colour (e.g. Textual's `$error` CSS variable — red by default).
- **Pros**: Users immediately know data was lost. They can decide to unpause or
  accept the loss. The count gives a sense of how much activity is happening.
- **Cons**: None — this is the already-specified behaviour. The enhancement is
  purely in the visual emphasis of the dropped count.
- **Effort**: Trivial (one CSS class + Rich markup change).

**Recommended** — implement exactly as specified in design-doc.md §3.4, with the
dropped count visually distinct (bold + warning colour) rather than inline plain text.

#### Option 5: Timestamp format — ISO 8601 full vs. HH:MM:SS.mmm short

- **Description**: The PRD (Q5 clarification) specifies ISO 8601 full datetime
  (`2026-05-07T14:23:01.042` — 23 characters). The alternative is a short time-only
  format (`14:23:01.042` — 12 characters), saving 11 characters per log line.
- **Pros of full ISO 8601**: Unambiguous across day boundaries; useful for log
  correlation with other systems; copy-paste into spreadsheets "just works".
- **Pros of short format**: 11 fewer characters per line means ~10% more log content
  visible per terminal column. For real-time debugging, the date portion is rarely
  relevant.
- **Cons of full format**: Verbose for interactive use; the date portion is rarely
  useful during a short debugging session.
- **Effort**: Both are trivial. A `--short-ts` flag or a `Settings.timestamp_format`
  field would let users choose.

**Phase 1 recommendation**: Accept the ISO 8601 decision as specified. Flag as a
Phase 2 quality-of-life option (`--ts-format short|full`). The target audience can
read ISO 8601 fluently and will appreciate unambiguous timestamps for log correlation.

#### Option 6: Color-coded log fields via Rich markup

- **Description**: Use Textual's Rich markup to color-code log fields —
  e.g. timestamp in dim white, sender ID in cyan, RORG in yellow, payload in green,
  RSSI in blue.
- **Pros**: Dramatically improves scan-ability. Users can find sender ID columns
  instantly without reading each line. Particularly useful in Scenario B (identifying
  unknown devices from a fast-scrolling log).
- **Cons**: Terminal colour support varies; some users run in restricted environments.
  Adds markup cost per line (negligible but not zero). Rich markup strings in the
  `RichLog` are slightly harder to grep externally.
- **Effort**: Low — each `RichLog.write_markup()` call uses Rich's `[cyan]...[/cyan]`
  syntax. No architecture changes required.

**Recommended** for Phase 1. The target audience uses color-capable terminals. Even
simple two-colour highlighting (sender ID in cyan, rest in default) would materially
improve readability at no cost. Suggested minimal palette:
```
[dim]2026-05-07T14:23:01.042[/dim]  [cyan bold]0xABCD1234[/cyan bold]  [yellow]RPS (0xF6)[/yellow]  70  [blue]RSSI -62 dBm[/blue]
```

#### Option 7: FakeDongle mode visual indicator

- **Description**: When running in FakeDongle mode, the header dongle status field
  shows `"DEMO (fake)"` or `"[bold yellow]DEMO MODE[/bold yellow]"` instead of the
  normal port path.
- **Pros**: Users running demos or tests can never mistake simulated traffic for real
  hardware. Scenario C (Carol's talk demo) benefits — the audience sees clearly that
  this is a replay.
- **Cons**: Slightly more header complexity. None material.
- **Effort**: Trivial — a one-line change in the status format.

**Recommended** — the distinction between real and fake traffic is a correctness
concern, not just a UX nicety.

---

### Recommendation

The overall UX direction is correct. The `tcpdump`-style interaction model, keyboard
bindings in the footer, inline filter, and PAUSED banner are all well-matched to the
target audience.

**Implement these enhancements in Phase 1:**

1. **Filter placeholder text**: `"e.g. ABCD1234 or 0xABCD1234"` in the `Input`
   widget. Zero implementation cost; eliminates the most common user error.

2. **Empty-filter notice**: When a filter is active and `_buffer` contains no matching
   entries, display a centred notice in the `RichLog` area:
   `"No telegrams match sender 0xABCD1234 — press Escape to clear filter"`.
   Without this, an empty log after filtering looks like a disconnected dongle.

3. **Filter active indicator**: Show `[FILTER: 0xABCD1234]` in the header or status
   line while a filter is applied. Users who scroll through the log after applying a
   filter need to know why some entries are missing.

4. **Pause overflow emphasis**: The `"N dropped"` portion of the PAUSED banner should
   use a warning colour (Textual `$error`). Plain text is easily missed in a fast
   debugging session.

5. **FakeDongle mode indicator**: Header dongle status shows `"DEMO (fake dongle)"`
   instead of a port path. Required for Scenario C correctness.

6. **Rich markup color coding for log fields**: Minimal: sender ID in cyan bold, RORG
   in yellow. Makes Scenario B (scanning for sender IDs) significantly faster.

7. **Auto-discovery feedback**: When no `--port` is given and discovery is running,
   show a brief spinner or status message in the header: `"Scanning for dongles..."`.
   Without this, the app appears to hang (could be 1–2 seconds — see scale.md OQ3).

---

## Constraints Identified

- **Filter must be exact match on `sender_int`, not fuzzy.** A partial hex string
  will silently produce no matches. The placeholder text and empty-filter notice
  together handle this without needing a format validator.
- **Pause buffer cap is 256, not unlimited.** Users who pause for a long time in a
  busy RF environment will lose older buffered telegrams. The UI must be explicit
  about this before overflow occurs, not only after.
- **Log re-render on filter apply blocks the event loop.** At 10,000 entries, this
  is a brief pause (~50–500 ms per scale.md). The user should see a momentary
  "Applying filter…" state rather than an unexplained freeze. Textual's `loading`
  reactive or a simple status-bar message covers this.
- **`c` (clear) is irreversible.** It clears both visible log and `_buffer`. No undo.
  A brief `"Log cleared (N entries)"` toast (Textual's `notify()`) gives the user
  confirmation of the destructive action without a confirmation prompt (which would
  break the tcpdump UX model).
- **No exit confirmation.** `q` exits immediately. This is correct for a CLI
  diagnostic tool — do not add a "are you sure?" prompt.

---

## Open Questions

1. **Filter input placement during high scroll rate.** If the log is scrolling rapidly
   when the user presses `f`, the input may be obscured. Should `f` implicitly pause
   the live display (but not the worker's internal buffering) until the input is
   dismissed? This would prevent the disorienting effect of a fast-scrolling log while
   the user is trying to type an 8-digit ID. *Recommendation: yes — open filter input
   activates implicit display-pause; Escape from filter restores live scrolling.*

2. **Clear (`c`) confirmation vs. notify.** A confirmation prompt would break flow; a
   `notify()` toast is non-blocking. Is a toast appropriate in the project's Textual
   style, or should clear be completely silent? *Recommendation: silent clear is
   acceptable for this audience; a toast is a nice-to-have.*

3. **`RichLog` scroll behavior on new telegrams.** Does `RichLog` auto-scroll to the
   bottom when new entries arrive, or does it stay at the user's current scroll
   position? If the user has scrolled up to inspect older entries, auto-scroll would
   be disruptive. Textual's `RichLog` auto-scrolls by default; a `scroll_end=True`
   toggle tied to whether the user has manually scrolled would improve the experience.
   *This may be an existing Textual widget behavior — verify before adding custom
   scroll logic.*

4. **`--fake` flag discoverability.** The PRD mentions `--fake` as a CLI flag for
   FakeDongle mode. Should `--help` output include an example showing how to demo
   without hardware? *Recommendation: yes — one example line in `--help` serves
   Scenario C users who don't yet know FakeDongle mode exists.*

5. **Footer key binding labels.** The current bindings are `q`, `c`, `p`, `f`.
   Textual's footer displays these with their actions. Are the action labels clear?
   Suggested labels: `q: Quit`, `c: Clear`, `p: Pause/Resume`, `f: Filter by ID`.
   The `f` label needs to hint at what "filter" means — "Filter by ID" is clearer
   than just "Filter".

---

## Integration Points

- **Integration analysis (integration.md):** The filter interaction model chosen here
  (inline input bar, Enter-to-apply) is already reflected in §3.3 of the design doc.
  The `set_filter(int | None)` API on `TelegramLog` (integration.md recommendation) is
  the correct hook for the filter-active indicator in the header.
- **Data model (data.md):** The `line: str` precomputed field in `FormattedTelegram`
  must include Rich markup if color coding is adopted. The formatter owns this string;
  the UX colour palette defined here feeds directly into `format_telegram()` in
  `src/enocean_async_tui/ui/formatters.py`.
- **Scalability (scale.md):** The filter re-render stall (OQ1 in scale.md) is the
  UX constraint named here as a constraint. The "Applying filter…" status indicator
  bridges both analyses — it is the user-facing side of the O(n) re-render cost.
- **Architecture/Implementation (design-doc.md):** The PAUSED banner (§5 task 9) and
  filter input (§5 task 10) are already in the task list. The enhancements here
  (colour-coded banner text, placeholder text, empty-filter notice, filter indicator)
  are additive to those tasks — they do not require new tasks, only clarification of
  the implementation detail within each existing task.
