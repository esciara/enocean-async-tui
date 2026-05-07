# Security Analysis

## Summary

Phase 1 Sniffer MVP has a narrow attack surface for a local CLI tool. The primary
threat vector is **malformed RF input**: any device within 868 MHz range can
transmit EnOcean telegrams that the dongle delivers to `enocean-async` for parsing.
If the parser does not handle malformed bytes robustly, a nearby attacker could
crash or disrupt the diagnostic session. Beyond that, the tool processes no network
traffic, stores no persistent data, requires no credentials, and elevates no
privileges — the attack surface is genuinely small.

The secondary risks are fixture file integrity (`burst-300.jsonl`), filter input
validation (hex string hygiene), and auto-discovery output trust. All three are
straightforward to address with defensive coding. The worst realistic outcome of
exploitation is a crashed terminal session — not data exfiltration, privilege
escalation, or remote code execution. The security profile is appropriate for a
local developer diagnostic tool.

---

## Analysis

### Key Considerations

- **Serial port access is gated by the OS.** On Linux, `/dev/ttyUSB*` access
  requires membership in the `dialout` (or equivalent) group. On macOS, `/dev/cu.*`
  access is user-accessible by default. This is a system-level control the app does
  not — and should not — replicate.
- **The primary untrusted input is RF traffic.** Anyone within 868 MHz range can
  transmit EnOcean telegrams. The dongle delivers raw bytes; `enocean-async` parses
  them. If the library does not validate all edge cases, a crafted telegram could
  trigger a parse exception, crash the worker, and halt the sniffer session.
- **Filter input is user-provided but low-risk.** The filter entry is parsed as an
  integer (hex → `int`). There is no SQL, no shell, no template — injection is not
  possible. The risk is a bad UX (confusing error message) rather than a security
  failure.
- **Phase 1 stores nothing permanently.** No local database, no log file, no config
  written to disk. All state is ephemeral in memory. There is no persistent
  sensitive data to protect.
- **EnOcean sender IDs are quasi-public device identifiers.** They are 32-bit
  hardware addresses, analogous to MAC addresses. Displaying them in a terminal is
  the tool's explicit purpose. Exposure via terminal replay or screen sharing is
  expected behavior, not a vulnerability.
- **FakeDongle fixture is a local file read at startup.** If `burst-300.jsonl` is
  world-writable or symlinked to an attacker-controlled location, malformed content
  could cause a parse error. Since the file is bundled with the package and accessed
  via `importlib.resources`, path traversal is not a concern after packaging.
- **No network I/O in Phase 1.** No sockets, no HTTP, no MQTT. The network attack
  surface is zero.

---

### Options Explored

#### Option 1: Propagate telegram parse errors — crash on malformed RF input

- **Description**: Let exceptions from `enocean-async`'s telegram parser propagate
  up through `SnifferWorker.run()`. An unhandled exception exits the worker and
  halts the sniffer session.
- **Pros**: Errors are visible immediately; no silent failures.
- **Cons**: A single malformed telegram — from a nearby attacker, faulty hardware,
  or library bug — crashes the diagnostic session. The user must restart the tool.
  In a busy RF environment (a building with many EnOcean devices), transient parse
  errors are plausible even without adversarial intent.
- **Effort**: Zero (this is the current default if no try/except is added).

**Not recommended.** A diagnostic tool that crashes on parse errors defeats its own
purpose.

#### Option 2: Catch parse errors per-telegram, log and continue (recommended)

- **Description**: Wrap the inner body of the `async for telegram in ...` loop in
  a `try/except Exception as exc:` block. On error, append a warning line to the
  `RichLog` (`"[yellow]⚠ Parse error: {exc}[/yellow]"`) and continue the loop.
  The sniffer session remains alive.
- **Pros**: A single malformed telegram cannot crash the session. The error is
  visible to the user without being fatal. Consistent with how `tcpdump` handles
  malformed packets (it logs and continues).
- **Cons**: Swallowing all exceptions may hide library bugs. Mitigation: log the
  full exception type and message; consider logging to stderr or a debug log for
  post-mortem analysis.
- **Effort**: Low — a four-line try/except around the inner loop body.

**Recommended.** This is the appropriate posture for a diagnostic tool reading
untrusted RF input.

#### Option 3: Strict filter input validation (hex-only accept)

- **Description**: The filter `Input` widget accepts only `[0-9A-Fa-f]` characters.
  Non-hex keypresses are rejected (or the input turns red with an inline error).
  On Enter, the value is validated as 1–8 hex digits before parsing.
- **Pros**: Eliminates the possibility of a confusing `ValueError` from `int(value, 16)`
  reaching the user as an unhandled exception. Gives immediate feedback on invalid
  characters.
- **Cons**: Slight implementation overhead (Textual `Input` validator or `on_key`
  filtering). Not a security necessity (the risk is UX confusion, not a security
  failure), but it improves robustness.
- **Effort**: Low — Textual's `Input` widget supports `validators` parameter.

**Recommended.** A `RestrictedInput` or a `Validator` subclass that rejects non-hex
characters is straightforward and closes the error path cleanly.

#### Option 4: Lenient filter input (strip non-hex, parse what's left)

- **Description**: On Enter, strip all non-hex characters from the filter input
  before parsing. Accept partial IDs (fewer than 8 digits) by zero-padding.
- **Pros**: More forgiving; users can paste `0xABCD 1234` with a space and still
  get a match.
- **Cons**: Silent data transformation may produce unexpected matches. If the user
  types `"ABCDEFGH"` and `H` is stripped, they get a filter for `0xABCDEF0` rather
  than an error. The behavior is surprising.
- **Effort**: Low.

**Not recommended.** The strict validation (Option 3) is clearer.

#### Option 5: FakeDongle fixture schema validation

- **Description**: When loading `burst-300.jsonl`, validate each line against a
  schema (required fields, value type and range checks) before constructing
  `FakeTelegram` objects. Fail with a clear error message if any line is malformed.
- **Pros**: Prevents a corrupt or tampered fixture from producing a runtime crash
  mid-demo (bad UX). Gives a clear error at startup rather than a cryptic exception
  later.
- **Cons**: Adds a small validation step at startup. Not a security necessity for
  a bundled fixture accessed via `importlib.resources`, but defensive programming
  is worthwhile.
- **Effort**: Low — a simple field-presence and type check per line; no third-party
  schema library needed.

**Recommended** for robustness, especially since `burst-300.jsonl` is also used in
integration tests. Malformed fixture data should produce a test failure at the
validation step, not a cryptic downstream error.

#### Option 6: Restrict `--port` to known device path patterns

- **Description**: Validate `--port` against a pattern (e.g., must start with
  `/dev/tty` on Linux/macOS, or match `COM\d+` on Windows) before passing to
  `serial.Serial()`.
- **Pros**: Prevents `--port /etc/passwd` or similar obviously wrong paths from
  producing confusing errors.
- **Cons**: Overly restrictive — legitimate serial ports on some systems may not
  match the pattern. `serial.Serial()` already produces a clear error on non-serial
  files. The OS enforces read permissions on `/dev` nodes regardless.
- **Effort**: Low, but the benefit is marginal.

**Not recommended.** The OS and serial library already handle this correctly. The
developer audience using `--port` will understand a `serial.SerialException` error.

---

### Recommendation

Three changes are warranted in Phase 1:

1. **Per-telegram exception handling in `SnifferWorker`** (Option 2): wrap the inner
   loop body in `try/except Exception`, log the error as a yellow warning line in
   `RichLog`, and continue. This is the most important security/robustness change —
   it prevents RF-sourced parse errors from crashing the session.

2. **Hex-only filter input validation** (Option 3): use Textual's `Input` validator
   or `restrict` parameter to accept only `[0-9A-Fa-f]` characters. Display an
   inline error on Enter if the result is empty or > 8 characters.

3. **FakeDongle fixture validation** (Option 5): validate required fields and types
   in `burst-300.jsonl` at load time. Fail clearly if the fixture is malformed,
   rather than crashing during a demo replay.

Options 1, 4, and 6 are not recommended.

---

## Constraints Identified

- **Serial port access is an OS-level permission gate.** The app cannot and should
  not attempt to bypass or replicate this. Users who lack `dialout` group membership
  will receive a `PermissionError` from `serial.Serial()`. This should be caught and
  displayed as a clear error message (not a raw Python traceback) with a hint to
  check group membership.
- **`enocean-async` is a third-party library parsing untrusted bytes.** The app
  cannot control the library's internal validation. The per-telegram try/except
  (Recommendation 1) is the correct defensive layer — it does not require auditing
  the library, only wrapping its output boundary.
- **EnOcean protocol ceiling limits DoS.** A nearby RF attacker can send at most
  ~120 telegrams/second (1% duty cycle limit on 868 MHz ISM). At that rate, the
  10,000-entry display buffer fills in ~83 seconds, after which the buffer cap
  prevents further memory growth. CPU load from parsing and rendering at 120/s is
  measurable but bounded by the display rate. This is a negligible denial-of-service
  risk for a local tool.
- **No sanitisation needed for log line display.** `RichLog.write_markup()` renders
  Rich markup. Sender IDs and payload hex are numeric/hex strings; they contain no
  Rich markup characters (`[`, `]`). RORG names come from a closed enum lookup —
  not from untrusted input. There is no XSS-equivalent risk in a terminal Rich
  output context. The only free-form string from untrusted input is the parse error
  message (exception string) in Option 2 — this should be escaped with
  `rich.markup.escape(str(exc))` before insertion into the markup string.
- **`importlib.resources` for fixture access prevents path traversal.** The design
  doc already specifies this (§1-E task 16). Ensure the implementation uses
  `importlib.resources.files(__package__).joinpath(...)` rather than constructing
  a path from `__file__` — the latter is fragile in editable installs.

---

## Open Questions

1. **`enocean-async` parse error taxonomy.** Does `enocean-async` define its own
   exception hierarchy (e.g., `EnoceanParseError`) or does it raise stdlib exceptions
   (`ValueError`, `struct.error`)? Knowing the exception type narrows the `except`
   clause to avoid swallowing unrelated errors. *Action: check `enocean-async` docs
   or source before implementing Option 2.*

2. **`PermissionError` on serial port open — how to surface it.** If the user lacks
   permission to open the serial port, the error occurs inside `DongleService`.
   Does Phase 0's error handling surface this as a status change (→ "error" state
   with a message) or does it propagate as an exception? *The UX dimension (ux.md)
   treats this as a fallback-to-FakeDongle path; the security dimension notes that
   the error message must distinguish "port not found" from "permission denied".*

3. **Rich markup injection from parse error strings.** If an `enocean-async`
   exception message contains Rich markup characters (`[red]`, `[/red]`, etc.),
   inserting it into `write_markup()` unescaped could corrupt the log display
   (no code execution risk, but visual corruption). Is `rich.markup.escape()` applied
   before inserting exception strings? *Action: confirm in implementation.*

4. **Logging to stderr for post-mortem.** When a parse error is caught per-telegram
   (Option 2), should the full traceback also be written to a debug log (e.g.,
   `~/.local/share/enocean-tui/debug.log` or stderr if `--debug` is set)? This
   would allow bug reports against `enocean-async` without cluttering the TUI log.
   *Recommendation: out of scope for Phase 1; accept a visible warning line in
   `RichLog` only.*

---

## Integration Points

- **UX Analysis (ux.md):** The per-telegram error warning line (Option 2) is a new
  log line type — it should be visually distinct from telegram lines (yellow, with a
  warning icon) but not disruptive. The filter input validator (Option 3) adds an
  error state to the `Input` widget that the UX dimension should style consistently
  with the rest of the UI.
- **Integration Analysis (integration.md):** The `PermissionError` handling at serial
  port open time (Open Question 2) is a gap in the integration analysis — it
  describes "port not found → FakeDongle modal" but does not distinguish permission
  errors from missing-device errors. Both should follow the same FakeDongle fallback
  path but with different status messages.
- **Data Model (data.md):** The `line: str` field in `FormattedTelegram` contains
  precomputed Rich markup. Confirm that `rich.markup.escape()` is applied to any
  field sourced from untrusted input (sender ID, payload hex) if those fields could
  ever contain Rich markup characters. In practice, hex strings cannot — but the
  formatter should be explicit about this assumption.
- **Scalability (scale.md):** The DoS-via-RF-flood scenario is bounded by the
  protocol ceiling and the 10,000-entry cap (see scale.md §Protocol ceiling).
  No additional mitigation is needed in Phase 1.
