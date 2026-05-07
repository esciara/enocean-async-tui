# Stakeholder Analysis

## Summary

The PRD identifies a narrow primary audience — "developers, makers, home automation enthusiasts,
system integrators" — but treats them as a single homogeneous group. In practice these are at
least four distinct cohorts with meaningfully different needs, and several additional stakeholders
(occupants of EnOcean-instrumented buildings, the enocean-async upstream library maintainers,
the Phase 0.5 frame-capture implementer, and an implicit support function) are not mentioned at
all. Most missing stakeholders do not create scope blockers for Phase 1 itself, but two
intersections produce genuine conflicts: (1) the long-session monitoring user's need for
unbounded log retention versus the short-session debugger's preference for fast, clean output;
and (2) the building-occupant privacy concern versus the maximally useful packet-capture design.
The privacy gap is the one finding that could cause post-launch friction beyond a simple feature
request.

---

## Findings

### Critical Gaps / Questions

**1. Building-occupant privacy is unaddressed**

EnOcean telegrams frequently encode personally identifiable behavioral data: motion sensor
activations, door/window state, occupancy, rocker-switch events (which may be security keyfobs
or access-control devices). A tool that captures and displays all wireless traffic on the bus
does this without any gating or consent mechanism. The PRD does not mention:
- Whether use of the tool in a shared or commercial building requires any access control
- Whether displaying raw sender IDs (permanently visible on screen) constitutes a privacy risk
- Whether captured data in the scroll-back buffer should be subject to any retention limit from
  a privacy perspective (the open question on log retention is framed only as a performance issue)

_Why this matters_: In some jurisdictions (EU, UK, parts of Canada) capturing wireless building
automation signals and associating them with occupant behavior could trigger GDPR / PIPEDA
obligations. Even if legal risk is low for an open-source CLI tool, the absence of any mention
means neither security nor legal has been consulted. If this tool is later adopted by a commercial
integrator in an EU context the gap will surface.

_Suggested clarifying question_: "Has the security/legal team reviewed whether displaying or
retaining EnOcean telegram data (motion, occupancy, access-control events) requires any
disclosure or consent mechanism? Should the tool display a disclaimer on launch in commercial
contexts?"

---

**2. Phase 0.5 implementer's output is Phase 1's undocumented dependency**

The bead context states "Phase 0.5: frame capture tool connecting to real dongle." The PRD's
Scenario C (demo without hardware) and Goal 6 (FakeDongle replay path) both require a recorded
session fixture in `FakeDongle`-compatible format. The Phase 0.5 implementer's decisions about
fixture format directly constrain Phase 1 implementation. The PRD does not name this person, does
not define the interface contract, and does not show Phase 0.5 as a formal dependency.

_Why this matters_: If Phase 0.5 and Phase 1 are developed in parallel by different polecats
(as the current dispatch model implies), there is no handshake point. Phase 0.5 may produce a
JSONL file while Phase 1 assumes a Python list of dicts, or vice versa. Either polecat could
block the other without either team knowing.

_Suggested clarifying question_: "Who is implementing Phase 0.5, and what is the fixture format
contract? Should Phase 0.5 deliver a fixture file to `tests/fixtures/` before Phase 1 starts, or
are they concurrent with a defined interface spec?"

---

### Important Considerations

**3. Long-session monitoring users (Bob's archetype) have different needs from short-session debuggers (Alice/Dave)**

The PRD's persona list treats all users identically but the scenarios reveal two distinct
operating modes:

| | Alice / Dave (debug session) | Bob (passive scan session) |
|---|---|---|
| Session length | Minutes | Hours |
| Log volume | Low–medium | High (dense EnOcean environments: 50–200 telegrams/min) |
| Log retention | Happy with 10k lines | 10k lines fills in <3 hours |
| Filter need | Single device focus | No filter (wants the full picture) |
| Export need | None | High (Scenario B ends with "copies to a spreadsheet") |

The 10,000-line cap works for Alice; Bob loses data silently. The Non-Goals exclude file logging
but Scenario B implies it. These aren't show-stoppers for Phase 1, but designing for Alice
exclusively makes the tool actively frustrating for Bob.

_Suggested question_: "Should the 10,000-line log cap be the configurable default (Open Question 1
already suggests 'configurable'), with `--max-lines 0` meaning unlimited? And is silent log
truncation acceptable for Phase 1, or should there be a visible indicator when lines are dropped?"

---

**4. System integrators have professional-tooling needs not acknowledged**

Home automation enthusiasts (Carol, Bob) and professional system integrators (who set up
EnOcean in commercial buildings) are bundled in the same persona. Professional integrators
typically need:
- Reliable operation over extended unattended sessions (hours/days)
- Some form of audit log or session export for client deliverables
- Multi-dongle capability for site surveys

All three are explicitly excluded (Non-Goals) or simply not discussed. That's fine for Phase 1,
but if "system integrators" are named as a target audience, they will land on the tool expecting
professional features and immediately hit non-goals. Either remove "system integrators" from the
target audience for Phase 1, or add a note that Phase 1 targets the hobbyist/developer end of
that spectrum.

---

**5. enocean-async upstream library is an unacknowledged stakeholder**

Phase 1 depends directly on `enocean-async` for `RawTelegram.rssi_dbm`, `RawTelegram.sender`,
`RORG` enum values, and (if base ID is in scope) `Gateway.base_id`. The library maintainers are
not named, not contacted, and the PRD treats the library API as fixed. If the library has bugs,
missing RORG values, or a breaking release during Phase 1 development, there is no identified
owner of the relationship to raise issues upstream.

_Suggested question_: "Is there a designated owner of the enocean-async upstream relationship?
If Phase 1 discovers a missing feature or bug in the library (e.g., RSSI absent for certain
frame types), who files the upstream issue and what is the fallback?"

---

**6. CI/CD system and future contributors (developer experience)**

The constraints section mandates mypy strict, ruff, TDD, and ≥80% coverage. These constraints
protect code quality but create friction for future contributors unfamiliar with the project.
The CLAUDE.md provides tooling guidance (`uv run`) but there is no CONTRIBUTING.md mentioned in
the PRD. Developer onboarding is a silent stakeholder gap: the first external contributor who
tries to run `uv run pytest` without knowing about `FakeDongle` or the test fixture dependency
will hit a confusing failure.

Not a Phase 1 blocker, but worth noting as a launch coordination item.

---

### Observations

**Support function is undefined**

The PRD mentions no support channel, no issue tracker, no documentation beyond the app itself.
When Alice can't identify why a telegram isn't appearing (is it the dongle? the filter? the
app?), where does she go? A developer tool with no troubleshooting guide will generate support
noise immediately after launch. A one-page README with common failure modes (wrong port,
dongle permissions on Linux, `uv run` not found) would address this for zero implementation cost.

**Launch coordination: Linux/macOS serial port naming needs a platform note**

The "60 seconds from zero" goal (Constraint section) assumes the user knows their serial port.
On Linux it's `/dev/ttyUSB0`; on macOS `/dev/cu.usbserial-*` (varies per device); on Windows
`COM3`. The gap between "developer who knows their OS" and "maker who just plugged in a dongle"
is wide. A `--list-ports` flag or at least a README section would prevent the #1 support
question at launch. Neither is in scope for Phase 1, but the stakeholder who needs to field that
question (whoever answers the project's issues) should know to prepare for it.

**Internal team dependency: test strategy alignment needed before implementation starts**

The chrome polecat's feasibility analysis identifies a concrete conflict: TDD is non-negotiable
but `RichLog` has no clean test API for asserting content. This is not just a technical problem —
it's a team alignment problem. The person who will write Phase 1 tests needs to agree with the
person who set the TDD constraint on what constitutes a valid Pilot test. This is an internal
stakeholder conversation that needs to happen before any code is written.

---

## Confidence Assessment

**Medium.** The stakeholder map for Phase 1 is thin but adequate for an MVP. The primary
user scenarios are concrete and the Non-Goals are explicit, which is more than most PRDs at
this stage. The two genuine confidence reducers are:

1. **Privacy (Low confidence)**: The privacy gap is the only finding here that has potential
   external consequence (legal, reputational) rather than just product-quality consequence. It's
   not a code-level blocker but it is the one thing that could generate friction after launch that
   isn't purely a feature request.

2. **Phase 0.5 coordination (Low-Medium confidence)**: If fixture format is not agreed before
   both phases start in parallel, Phase 1's demo path will be broken at integration time with
   no clear owner of the fix.

Everything else (integrator vs. enthusiast mismatch, upstream library ownership, developer
onboarding) is a post-launch quality issue, not a Phase 1 blocker. The PRD can ship to
implementation after resolving Critical Gaps 1 and 2 from the scope and feasibility analyses,
plus the Phase 0.5 coordination question raised here.
