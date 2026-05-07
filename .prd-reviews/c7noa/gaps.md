# Missing Requirements

## Summary

The PRD is scoped tightly around the happy-path sniffer experience. Several entire requirement
categories are absent: there is no mention of accessibility, no error state requirements for
malformed telegram data, no specification of what happens when the serial port path is wrong,
and no admin/diagnostic surface for developers debugging the app itself. These are the gaps most
likely to surface as post-launch surprises or support tickets.

## Findings

### Critical Gaps / Questions

**1. Error state: invalid or unknown serial port**
- The PRD describes the dongle-absent "no dongle" modal from Phase 0 but says nothing about a
  user passing `--port /dev/ttyXXX` where the port does not exist, is not a dongle, or is busy.
- Why this matters: This is the most common first-run failure. Without a specified error message
  or recovery path, every implementation will invent its own behaviour.
- Question: When `--port` is given but cannot be opened, what should the UI show? An error modal?
  A log line? Automatic fallback to FakeDongle?

**2. Telegram decode errors / malformed data**
- The PRD assumes all telegrams are well-formed. `enocean-async` may emit parse errors, partial
  reads, or unknown RORGs. None of these cases are specified.
- Why this matters: A real EnOcean bus has noise. An unknown RORG should probably display as
  `UNK (0xXX)` rather than crashing the sniffer. Without a spec, engineers will either drop or
  crash on unknown data.
- Question: How should the UI handle an unknown RORG code? A malformed telegram body?

**3. RORG display for extended formats (MSC, SYS-EX, Smart ACK)**
- The PRD lists "RPS / 1BS / 4BS / VLD / …" as the RORG display set. EnOcean also uses MSC
  (Manufacturer Specific Command), SYS-EX (System Extended), Smart ACK frames, and the
  Signal telegram type. These are not mentioned.
- Why this matters: A developer debugging Smart ACK registration will see nothing useful if
  the sniffer silently ignores those RORG values.
- Question: Should all RORG bytes be shown (even unknown ones), or only the named set?

**4. Keyboard shortcut conflicts with Textual defaults**
- Textual has default bindings (`ctrl+c` to quit, `ctrl+q` to quit, etc.). The PRD defines
  `q` to quit but doesn't account for focus state — will `q` quit even when the filter Input
  widget has focus? Will `ctrl+c` also quit? Are there reserved bindings that must be avoided?
- Why this matters: Conflicting bindings cause hard-to-reproduce bugs and confuse users.
- Question: Define the binding scope rules. Does `q` quit regardless of focused widget?

**5. Multi-platform serial port names**
- The PRD uses `/dev/ttyUSB0` as the example. On macOS the path is `/dev/cu.usbserial-*`;
  on Windows it is `COM3`. The app's Settings / CLI default is not specified for each platform.
- Why this matters: The "demo-able in 60 seconds" goal fails on macOS if the default port is
  a Linux path that doesn't exist.
- Question: What is the default `--port` value on macOS and Windows? Is auto-detection in scope?

### Important Considerations

**6. First-run experience: no dongle AND no explicit --port flag**
- Scenario C describes running without `--port` → "no dongle" modal → accept FakeDongle. But
  the logic for "no dongle detected without explicit port" vs "port given but wrong" is different.
  The PRD does not distinguish these paths.
- Suggestion: Define the decision tree: no arg → auto-detect → if none found → modal. Explicit
  arg → try to open → if fail → error (not modal?).

**7. Log file / export path**
- The PRD explicitly non-goals "no structured file logging" but does not mention clipboard copy,
  selection, or text export. Users debugging will want to save a session. Even a simple
  "copy visible log to clipboard" binding would be high value.
- Suggestion: Decide explicitly: is clipboard copy out of scope for Phase 1?

**8. RSSI availability per telegram**
- Goal 2 requires RSSI per line. Not all `enocean-async` telegram objects may carry RSSI (it
  depends on whether the dongle reports sub-telegram information). If RSSI is unavailable for
  some telegrams, what should the display show? `–`? `N/A`?
- Suggestion: Verify `enocean-async` always provides RSSI and define fallback display value.

**9. Window resize / terminal resize handling**
- Textual applications must handle `SIGWINCH` / terminal resize events. The `RichLog` should
  reflow. This is implicit in Textual's design but no PRD requirement acknowledges it, meaning
  there is no test coverage obligation.
- Suggestion: Add a non-functional requirement: "app must function correctly at 80×24 minimum
  terminal size and handle dynamic resize without crash."

### Observations

- The PRD doesn't mention Python packaging / entry-point behaviour on first install. The README
  note says `uv run enocean-tui` but the PRD goal says `uv run enocean-tui --port /dev/ttyUSB0`.
  The CLI argument parsing spec (argparse vs Click vs Textual's own CLI) is absent.
- Accessibility (screen reader, high-contrast mode) is entirely absent. Even a single
  non-goal statement ("accessibility not addressed in Phase 1") would prevent future confusion.
- No mention of signal handling: `SIGTERM`, `SIGHUP`. Graceful shutdown on signal is
  usually expected for any CLI tool.

## Confidence Assessment

**Medium-Low.** The PRD covers what the feature does when everything works. The error handling
layer — wrong port, malformed data, unknown RORG — is largely unspecified. These are predictable
failure modes for a serial I/O tool and should be addressed before implementation to avoid
divergent implementations per engineer.
