# PRD Alignment Round 2: Constraints + Non-Goals
## Phase 1 Sniffer MVP

**PRD:** `.prd-reviews/sniffer-mvp/prd-draft.md`
**Plan:** `.designs/sniffer-mvp/design-doc.md`
**Reviewer:** rust (combined A + B — sling unavailable to polecats)
**Date:** 2026-05-07
**Based on:** Round 1 changes applied by nitro (eat-wfs-eam6s)

---

## Part A — Constraints Compliance

PRD defines 7 constraints. Each is checked against the post-round-1 design.

### Constraint Table

| Constraint | Status | Notes |
|------------|--------|-------|
| C1: Async-only, no blocking I/O | **VIOLATED** | §1-E auto-discovery calls `comports()` synchronously — see M1 |
| C2: Single event loop | **VIOLATED** | Same root cause as C1: `comports()` on event loop thread blocks it |
| C3: Phase 0 API fixed | RESPECTED | §4.1 explicitly: no changes to DongleService/FakeDongle/Settings |
| C4: No new runtime deps | RESPECTED | §9 explicitly: "No new runtime dependencies" |
| C5: TDD non-negotiable | RESPECTED | §6 TDD requirement added in round 1 |
| C6: mypy strict clean | RESPECTED | §6 quality gate added in round 1 |
| C7: Demo-able in 60 seconds | UNADDRESSED | §1-E helps but no explicit validation — see S1 |

### Detailed Findings

**M1 — C1+C2: Auto-discovery blocks the event loop (MUST-FIX)**

`serial.tools.list_ports.comports()` is a synchronous, potentially blocking call
(it enumerates OS-level serial devices). Running it directly on the Textual/asyncio
event loop thread violates both C1 (async-only) and C2 (single event loop — no
blocking).

The design describes the feature (§1-E, §4.2) but does not specify how the scan is
executed asynchronously.

**Required fix:**
- §1-E must specify: `await asyncio.to_thread(serial.tools.list_ports.comports)`
- Also specify detection mechanism: USB VID/PID matching against known EnOcean
  dongle IDs — no probe commands sent to the device (passive enumeration only)
- §6 tests for auto-discovery must verify the `asyncio.to_thread` wrapping via mock
- Add to §10 Risks: auto-discovery blocking the event loop (High risk without fix)

---

**S1 — C7: Demo-speed constraint not validated (SHOULD-FIX)**

The PRD requires a first-time user to reach a live sniffer in ≤60 seconds. §1-E
auto-discovery directly addresses the main friction point (no need to find the port).
However, no explicit acceptance criterion or test validates this target.

**Required fix:**
- §7 (Open Questions) should record C7 as resolved: auto-discovery eliminates
  manual port lookup; no synchronous startup gates block first telegram
- Note that this is an acceptance criterion, not a unit test: end-to-end demo speed
  cannot be automated but should be part of manual pre-release checklist

---

## Part B — Non-Goals Enforcement

PRD defines 8 non-goals. Each plan section is checked for scope creep.

### Non-Goals Table

| Non-Goal | Status | Notes |
|----------|--------|-------|
| NG1: No telegram decoding | CLEAN | RORG name lookup is required by Goal 2; payload raw hex only |
| NG2: No device registry | CLEAN | In-memory buffer only; no persistence |
| NG3: No teach-in flow | CLEAN | Not mentioned anywhere |
| NG4: No outgoing commands | BORDERLINE | Auto-discovery mechanism unspecified — see S2 |
| NG5: No multi-dongle support | BORDERLINE | Selection modal implies multi-dongle awareness — see S3 |
| NG6: No structured file logging | CLEAN | Not mentioned |
| NG7: No MQTT / remote access | CLEAN | Not mentioned |
| NG8: No RORG/payload content filtering | CLEAN | §3.3 sender-ID filter only |

### Detailed Findings

**S2 — NG4: Auto-discovery detection mechanism unspecified (SHOULD-FIX)**

The non-goal "No outgoing commands" prohibits sending commands to the dongle.
§1-E says "scan serial ports for EnOcean dongles" but doesn't specify how a port
is identified as an EnOcean dongle. If identification requires sending a probe
command (e.g., `CO_RD_VERSION`), that would violate NG4.

The correct mechanism is USB VID/PID matching — `serial.tools.list_ports.comports()`
returns hardware metadata (vendor ID, product ID) for USB-serial adapters without
opening the port or sending any commands.

**Required fix:**
- §1-E must specify: "Detection uses USB VID/PID matching only — no port is opened
  and no commands are sent during discovery"
- This also resolves the C1+C2 concern: the entire scan is a single `comports()` call
  wrapped in `asyncio.to_thread`, not a multi-step probe loop

---

**S3 — NG5: Selection modal needs scope clarification (SHOULD-FIX)**

The PRD non-goal states "No multi-dongle support." §1-E includes "If multiple [found]:
present selection modal." At first glance this appears to conflict.

However, "no multi-dongle support" means no simultaneous reading from multiple dongles.
The selection modal lets the user pick exactly one dongle from several detected, then
connects to that one. This is not multi-dongle use; it is a necessary fallback for a
common real-world scenario (laptop with multiple USB-serial adapters).

**Required fix:**
- §8 Non-Goals should clarify the distinction: the selection modal is single-dongle
  selection, not simultaneous multi-dongle use; exactly one dongle is always active
- §1-E task 15 should note: "single-dongle selection, not multi-dongle simultaneous use"

---

## Findings Summary

### MUST-FIX

**M1 — C1+C2: Auto-discovery serial scan must use `asyncio.to_thread`**

`comports()` is synchronous blocking. Running on the event loop violates both C1 and C2.
Also clarify that detection uses USB VID/PID only — no probe commands (NG4 compliance).

---

### SHOULD-FIX

**S1 — C7: Record demo-speed resolution in §7**

Auto-discovery resolves C7 in practice; add explicit resolution note to §7 so the
constraint is visibly addressed.

**S2 — NG4: Specify VID/PID detection in §1-E**

State that no port is opened and no commands are sent during auto-discovery scan.
Clarifies NG4 compliance and reduces ambiguity for the implementer.

**S3 — NG5: Clarify selection modal scope in §8 and §1-E**

Distinguish "select one from several" from "use multiple simultaneously."
Resolves apparent conflict with NG5 non-goal.

---

## Actions Applied to Design Doc

- [x] M1: Added `asyncio.to_thread` requirement to §1-E task 13 (C1+C2 annotation)
- [x] M1: Added USB VID/PID detection specification to §1-E (NG4 compliance)
- [x] M1: Added high-risk row to §10 Risks table (auto-discovery event-loop blocking)
- [x] M1: Tightened §6 coverage note to reference `asyncio.to_thread` mock verification
- [x] S1: Added C7 demo-speed resolution row to §7 Open Questions table
- [x] S2: (covered by M1 — VID/PID spec added to §1-E)
- [x] S3: Added clarifying note to §8 Non-Goals (selection modal = single-dongle pick)
- [x] S3: Added note to §1-E task 15 (single-dongle selection, not multi-dongle use)
- [x] Updated §1 status line to reflect round 2 review
