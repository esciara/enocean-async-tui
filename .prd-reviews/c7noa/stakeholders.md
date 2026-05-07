# Stakeholder Analysis

## Summary

The PRD correctly identifies developers, makers, home automation enthusiasts, and system
integrators as the target users. However, it conflates these groups as a single persona, which
masks real conflicts: a system integrator needs stable field reliability and minimal dependencies,
while a developer/maker wants rich debug output. Three missing stakeholder groups have concrete
requirements that would change the PRD: package maintainers (PyPI distribution), downstream
library users (enocean-async), and corporate IT / restricted networks.

## Findings

### Critical Gaps / Questions

**1. System integrators vs. developers have conflicting needs**
- A system integrator running the sniffer on a Raspberry Pi on a client site needs:
  - Minimal startup overhead (not 1–2 seconds)
  - No unexpected crash on unknown telegrams
  - Works reliably on serial ports that may disconnect/reconnect during the session
- A developer/maker wants:
  - Rich debug output (raw hex, RORG names, RSSI)
  - Python tracebacks on error (not suppressed)
  - Easy filter and scroll
- These needs are mostly complementary but conflict on error handling: a developer wants verbose
  errors; an integrator wants graceful silent recovery.
- Question: Who is the primary persona? This determines whether error verbosity is configurable
  or fixed.

**2. Package maintainer / PyPI distribution stakeholder is absent**
- The PRD makes no mention of how the tool will be distributed. Is it pip-installable? Only
  via uv? Is there a PyPI package planned?
- Why this matters: The "demo-able in 60 seconds" goal is only achievable if installation is
  frictionless. `uv run enocean-tui` assumes uv is installed. For integrators without uv,
  the onboarding story is broken.
- Question: Is PyPI distribution in scope for Phase 1? If not, what is the stated installation
  path for non-uv users?

**3. `enocean-async` library maintainers are an implicit stakeholder**
- Phase 1 depends on the public API of `enocean-async`. If Phase 1 discovers RSSI is not
  exposed, or if the telegram model lacks a field Phase 1 needs, the maintainers need to be
  engaged or the library patched.
- No mention of this dependency relationship exists in the PRD.
- Question: Is there a pinned or verified-compatible version of `enocean-async` for Phase 1?
  Who is the contact if a library limitation blocks Phase 1?

### Important Considerations

**4. Home Assistant users as an adjacent persona**
- The PRD positions the tool as an alternative to Home Assistant for debugging. HA users who
  also use this tool will expect terminology consistency (device names, EEP naming conventions).
- HA uses different RORG naming conventions in some cases. If `enocean-tui` uses different
  names, users will be confused.
- Suggestion: Document which RORG naming convention is used (EnOcean spec official names vs.
  HA-style names).

**5. Support/ops persona is absent**
- The "support team" for this tool is the developer themselves (it's open source). But the
  "operator" persona — someone who runs the sniffer 24/7 and needs to know if it crashes —
  has no requirements in the PRD.
- No mention of: log file, crash report, exit code on error, or monitoring hook.
- Suggestion: Even for an open-source tool, define the exit code contract: `0` = clean quit,
  non-zero = error. This enables scripting.

**6. Contributors / maintainers (GitHub) as stakeholders**
- The PRD says nothing about how contributors will extend the tool (adding a new RORG, changing
  the log format). The architecture section describes the implementation approach but not the
  extension points.
- Suggestion: Add a note: "log format and RORG names are configurable via a constants module,
  not scattered through display code" — this will prevent future refactoring pain.

### Observations

- Corporate users on restricted networks may not be able to install packages via uv/pip. This
  is probably not a Phase 1 concern but worth a non-goal statement.
- The "makers" persona (Arduino-style hobbyists) may have Windows as their primary platform.
  Windows serial port handling (`COM3`, `pyserial` driver requirements) is not mentioned.
- The PRD targets "the open-source Python ecosystem" as a gap to fill. This frames the tool
  as a community project, not a commercial product. That framing affects decisions about
  telemetry, crash reporting, and update notifications — all of which should be non-goaled
  explicitly.
- The "why now" section (Phase 0 ships → Phase 1 is first demo-able product) is strong
  and well-reasoned. The stakeholder narrative would benefit from one sentence acknowledging
  the existing `enocean` (non-async) library's users as potential adopters.

## Confidence Assessment

**Medium.** The primary user persona is clear enough for implementation. The missing stakeholders
(package maintainers, enocean-async library, Windows users) are low-severity for Phase 1 but
medium-severity for Phase 1 launch. The conflicting integrator vs. developer needs on error
verbosity is the one decision that should be made before error-handling code is written.
