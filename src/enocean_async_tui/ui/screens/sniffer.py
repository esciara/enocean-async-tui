"""SnifferScreen — Phase 1-B task 5.

Performance note (task 4.5 spike, 2026-05-07):
  RichLog.write() x 10 000 = ~488 ms in run_test() (size known, real rendering).
  Exceeds the 200 ms threshold — batch_write() helper required.
  Use batch_write() for all bulk writes (e.g. filter re-renders) to keep the
  event loop responsive.
"""

from __future__ import annotations

import asyncio
from collections import deque

from rich.markup import escape as markup_escape
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Input, RichLog, Static

from enocean_async_tui.ui.formatters import FormattedTelegram, format_telegram
from enocean_async_tui.ui.messages import ParseWarning, TelegramReceived

_CHUNK_SIZE = 100
_MAX_LINES = 10_000


async def batch_write(log: RichLog, lines: list[str]) -> None:
    """Write *lines* to *log* in chunks, yielding to the event loop between chunks.

    Prevents blocking the event loop when writing thousands of entries at once,
    e.g. during retroactive filter re-renders.
    """
    for offset in range(0, len(lines), _CHUNK_SIZE):
        for line in lines[offset : offset + _CHUNK_SIZE]:
            log.write(line)
        await asyncio.sleep(0)


class PausedBanner(Static):
    """Status banner displayed while the sniffer is paused."""

    queued: reactive[int] = reactive(0)
    dropped: reactive[int] = reactive(0)

    def render(self) -> str:
        if self.dropped > 0:
            return f"PAUSED — {self.queued} queued ([bold red]{self.dropped} dropped[/bold red])"
        return f"PAUSED — {self.queued} queued"


class FilterInput(Input):
    """Skeleton filter input widget. Full implementation deferred to task C2."""


class SnifferScreen(Screen[None]):
    """Live EnOcean telegram sniffer screen.

    Handles TelegramReceived messages by formatting, filtering, and appending
    to both the in-memory _buffer and the RichLog widget.
    """

    DEFAULT_CSS = """
    SnifferScreen {
        layout: vertical;
    }
    #sniffer-log {
        height: 1fr;
    }
    PausedBanner {
        height: 1;
        background: $surface;
        color: $warning;
        text-align: center;
    }
    FilterInput {
        height: 1;
    }
    """

    filter_id: reactive[int | None] = reactive(None)

    def __init__(self) -> None:
        super().__init__()
        self._buffer: deque[FormattedTelegram] = deque(maxlen=_MAX_LINES)

    def compose(self) -> ComposeResult:
        yield RichLog(id="sniffer-log", max_lines=_MAX_LINES, wrap=False, markup=True)
        yield PausedBanner(id="paused-banner")
        yield FilterInput(
            id="filter-input",
            placeholder="e.g. ABCD1234 or 0xABCD1234",
        )

    def on_mount(self) -> None:
        self.query_one("#paused-banner", PausedBanner).display = False
        self.query_one("#filter-input", FilterInput).display = False

    def on_telegram_received(self, message: TelegramReceived) -> None:
        """Format incoming telegram, apply live filter, append to buffer and log."""
        ft = format_telegram(message.telegram)
        if self.filter_id is not None and ft.sender_int != self.filter_id:
            return
        self._buffer.append(ft)
        self.query_one("#sniffer-log", RichLog).write(ft.line)

    def on_parse_warning(self, message: ParseWarning) -> None:
        """Write a yellow warning line for per-telegram parse errors; never crash."""
        safe_msg = markup_escape(str(message.exc))
        self.query_one("#sniffer-log", RichLog).write(f"[yellow]WARNING: {safe_msg}[/yellow]")

    async def apply_filter(self, filter_id: int | None) -> None:
        """Apply or clear a sender-ID filter retroactively from _buffer."""
        self.filter_id = filter_id
        log = self.query_one("#sniffer-log", RichLog)
        log.clear()

        if filter_id is None:
            lines = [ft.line for ft in self._buffer]
        else:
            lines = [ft.line for ft in self._buffer if ft.sender_int == filter_id]

        if not lines and filter_id is not None:
            log.write("[dim italic]No matching entries for current filter.[/dim italic]")
            return

        await batch_write(log, lines)
