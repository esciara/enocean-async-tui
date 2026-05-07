# Technical Feasibility

## Summary

Phase 1 (Sniffer MVP) is buildable on the Phase 0 foundation with moderate effort. The core architecture is already in place: `DongleService.telegrams()` is a live async iterator, `RawTelegram` already exposes sender, RORG, payload, and RSSI, and the app's `_telegrams_worker` stub is exactly where Phase 1 plugs in. The single-event-loop constraint is already enforced. There are no fundamental architectural blockers.

Two concerns stand out. First, writing reliable Textual Pilot test assertions against `RichLog` content is non-trivially supported by the Textual API — this is the most likely place where "TDD is non-negotiable" meets an engineering surprise that could double implementation time. Second, the PRD's header requirement (show dongle base ID) has an implicit coupling gap: `DongleService` does not expose `base_id`, but the underlying `Gateway` fetches it at startup. Surfacing it requires extending the `Dongle` protocol, which the PRD doesn't mention.

## Findings

### Critical Gaps / Questions

**1. Phase 0.5 scope is undefined in the PRD**

The bead context says "Phase 0.5: frame capture tool connecting to real dongle" but the PRD draft contains no Phase 0.5 section. It is unclear:
- Whether Phase 0.5 is a prerequisite for Phase 1 (e.g., it produces the JSONL recording fixture that FakeDongle needs for Scenario C)
- What the deliverables, interfaces, or acceptance criteria are
- Whether it is a separate polecat assignment or bundled here

_Why this matters_: If Phase 0.5 is the capture tool that creates `FakeDongle` recordings, Phase 1's Scenario C ("replayed telegrams in demo mode") cannot pass its test without a bundled fixture file. Phase 1 currently has no fixture.

_Suggested question_: Is Phase 0.5 a separate deliverable that precedes Phase 1? What does it produce, and is Phase 1 blocked on it?

---

**2. Base ID not surfaced through `DongleService` or the `Dongle` protocol**

The PRD requires the header to display the dongle's base ID (Goal 3). The underlying `Gateway` fetches `base_id` at `start()` via `CO_RD_IDBASE`, and `gateway.base_id` is available after connect. However:
- `DongleService` does not expose `base_id` as a property
- The `Dongle` protocol (shared with `FakeDongle`) has no `base_id` member
- `DongleService` does not expose the underlying `Gateway` object

Displaying base ID requires either adding `base_id: BaseAddress | None` to the `Dongle` protocol and both implementations, or a different mechanism. The PRD says "Phase 0 foundation is fixed — additions only", so this is legal, but it is unacknowledged prerequisite work.

_Why this matters_: Without this addition, the header can only show "–" permanently. `FakeDongle` also needs a synthesized base ID for tests. This is ~1–2 hours of work but must be done before the header feature can be implemented.

_Suggested question_: Should `base_id` be added to the `Dongle` protocol in Phase 1? If so, what base ID should `FakeDongle` return?

---

**3. Testing `RichLog` content via Textual Pilot is not straightforward**

The PRD mandates TDD with Pilot tests asserting log line content (e.g., "assert all 3 telegrams appear in the `RichLog`"). Textual's `RichLog` widget stores rendered Rich text, not raw strings. There is no documented public API for reading back lines as plain text from a test. Options are:
- Subclass `RichLog` to shadow writes and track a parallel list of plain strings for test assertions
- Use `app.query_one(RichLog).lines` if it exists (undocumented, version-dependent)
- Use a snapshot/screenshot comparison (brittle, slow)

The Phase 0 tests use `header.status` (a reactive attribute) for assertions — clean, stable. That approach does not extend naturally to log content.

_Why this matters_: If the test strategy isn't settled before implementation starts, the developer may write production code and then discover the test approach doesn't work, requiring a refactor. TDD means the test comes first — a test that can't make assertions is a non-starter.

_Suggested question_: What is the agreed test strategy for asserting `RichLog` content? Is a `RichLog` subclass with a `lines: list[str]` accumulator acceptable?

---

### Important Considerations

**4. `filter_id` type must be `int`, not `EURID`, for mypy strict compliance**

The PRD proposes `filter_id: int | None` on the app. `RawTelegram.sender` is typed as `EURID | BaseAddress`. Under mypy strict, comparing `telegram.sender == filter_id` (where `filter_id: int`) is a type error unless the comparison is `int(telegram.sender) == filter_id`. This is a small but real issue that will fail CI if not handled upfront. Alternatively, `filter_id` could be typed `EURID | None` with appropriate construction from user input.

**5. Pause buffer has no stated size limit; burst-on-resume may stutter the UI**

The DongleService queue (256 entries) acts as the upstream buffer. While paused, the sniffer worker's local `deque` accumulates additional telegrams. If the user pauses for an extended period, the worker deque could hold thousands of entries. On resume, the app receives a burst of `TelegramReceived` messages within a single event-loop cycle, potentially causing a render stutter or log line overflow. The PRD does not specify a max pause buffer size or what happens when it fills.

**6. Demo scenario requires a bundled recording fixture (links to Phase 0.5)**

`FakeDongle(realtime=True)` with `recording=None` emits zero telegrams. Scenario C ("Fake dongle mode, sniffer shows replayed telegrams") requires a JSONL recording file bundled with the package. Currently no such fixture exists in `tests/` or `src/`. If Phase 0.5 produces this fixture, it must be available before Phase 1 can pass this test.

**7. RORG values with no clean name**

`RORG` is an enum; the PRD proposes displaying `RORG.name`. Standard RORG values (RPS=0xF6, 1BS=0xD5, 4BS=0xA5, VLD=0xD2) have names defined. However, the EnOcean spec includes additional RORG values (signal telegram, manufacturer-specific, etc.) that may not be in the enum or may have non-human-friendly names. Display code should guard against missing enum members and fall back to hex for unknown RORG values.

---

### Observations

**The core loop is already working.** `DongleService.telegrams()` emits live `RawTelegram` objects, `RawTelegram.rssi_dbm` already handles the 0xFF sentinel and returns `int | None`, and `_telegrams_worker` in `app.py` is exactly the hook point. Wiring the log display is straightforward once the test strategy is settled.

**`RichLog` is a built-in Textual widget** (introduced well before 8.2.3). The `max_lines` parameter handles log retention (Open Question 1). Defaulting to 10,000 lines is fine.

**Key bindings `q`, `c`, `p`, `f`** are all standard Textual `BINDINGS` entries with corresponding `action_*` methods. No significant complexity there.

**The filter UX (Open Question 5 — single sender ID)** is the right scoping. A single 8-hex-digit `Input` widget is straightforward. The only non-obvious detail is focus management: pressing `f` must focus the Input, Escape must return focus to the main log. Textual handles this cleanly via `Screen.set_focus()`.

**RSSI display** can show `"–"` when `rssi_dbm is None`. The PRD's preference for raw dBm over icons (Open Question 3) is the right call for a developer tool.

**The auto-reconnect path is already tested in Phase 0.** Phase 1 inherits it for free — the sniffer worker's async iterator from `DongleService.telegrams()` will naturally terminate when the dongle closes, and a new worker is started on reconnect (or the worker should be restarted; this lifecycle detail needs clarification but is not a blocker).

## Confidence Assessment

**Medium-High.** The foundational layer is solid and the implementation path is clear for all features except RichLog testability (which is the main uncertainty) and base ID surfacing (which is a known gap with a known fix). There are no requirements that are technically impossible. The main risks are:
1. The RichLog test strategy discovery (could add 0.5–1 day if the naive approach fails)
2. Phase 0.5 dependency (blocks the demo scenario if Phase 0.5 hasn't shipped)
3. The base ID protocol extension (small but must be deliberate)

Everything else in the PRD is straightforward given the Phase 0 foundation.
