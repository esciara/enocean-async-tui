"""Benchmark: RichLog.write() x 10 000 baseline and batch_write() helper correctness.

Spike result (2026-05-07, Apple M-series):
  Unbatched: ~488 ms — exceeds 200 ms threshold.
  batch_write() (chunk=100, asyncio.sleep(0) between chunks) prevents event-loop
  stalling for retroactive filter re-renders in SnifferScreen.
"""

from __future__ import annotations

import time

import pytest
from textual.app import App, ComposeResult
from textual.widgets import RichLog

from enocean_async_tui.ui.screens.sniffer import batch_write

_N = 10_000
_SAMPLE = "[bold green]{:08X}[/bold green] RORG=0x35 data=0xABCD1234 status=0x00"


class _BenchApp(App[None]):
    def compose(self) -> ComposeResult:
        yield RichLog(id="log", max_lines=_N, wrap=False)


@pytest.mark.slow
async def test_richlog_unbatched_baseline() -> None:
    """Document unbatched RichLog.write() x 10 000 timing as a regression baseline.

    Expected: ~488 ms (exceeds 200 ms threshold — batch_write() required).
    The generous upper bound of 5 000 ms guards only against catastrophic regressions.
    """
    app = _BenchApp()
    async with app.run_test(size=(120, 40)) as pilot:
        log = pilot.app.query_one("#log", RichLog)
        t0 = time.perf_counter()
        for i in range(_N):
            log.write(_SAMPLE.format(i))
        elapsed_ms = (time.perf_counter() - t0) * 1_000
    # Generous upper bound — catches only catastrophic Textual regressions.
    assert elapsed_ms <= 5_000, f"RichLog.write() x {_N} took {elapsed_ms:.0f} ms (catastrophic regression)"


async def test_batch_write_writes_all_entries() -> None:
    """batch_write() must deliver all entries to the RichLog."""
    n = 500  # Smaller N for non-slow test
    lines = [_SAMPLE.format(i) for i in range(n)]
    app = _BenchApp()
    async with app.run_test(size=(120, 40)) as pilot:
        log = pilot.app.query_one("#log", RichLog)
        await batch_write(log, lines)
    assert len(log.lines) == n
