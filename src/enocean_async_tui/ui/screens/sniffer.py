"""SnifferScreen — Phase 1-B task 5.

Performance note (task 4.5 spike, 2026-05-07):
  RichLog.write() x 10 000 = ~488 ms in run_test() (size known, real rendering).
  Exceeds the 200 ms threshold — batch_write() helper required.
  Use batch_write() for all bulk writes (e.g. filter re-renders) to keep the
  event loop responsive.
"""

from __future__ import annotations

import asyncio
import re
from collections import deque
from typing import TYPE_CHECKING, ClassVar

from rich.markup import escape as markup_escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import Key
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Input, RichLog, Static

from enocean_async_tui.ui.formatters import FormattedTelegram, format_telegram
from enocean_async_tui.ui.messages import FilterChanged, ParseWarning, PauseBufferUpdated, TelegramReceived

if TYPE_CHECKING:
    from enocean_async_tui.ui.workers.sniffer import SnifferWorker

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
    """Hex sender-ID filter input.

    Shows 'pending' CSS class while visible to signal filter not yet applied.
    Key routing is handled by SnifferScreen.on_key to avoid focus scope issues
    when SnifferScreen is embedded as a widget rather than pushed as a screen.
    """


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
    FilterInput.pending {
        color: $text-muted;
        text-style: italic;
    }
    """

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        ("q", "quit", "Quit"),
        ("c", "clear", "Clear"),
        ("p", "toggle_pause", "Pause/Resume"),
    ]

    filter_id: reactive[int | None] = reactive(None)

    def __init__(self) -> None:
        super().__init__()
        self._buffer: deque[FormattedTelegram] = deque(maxlen=_MAX_LINES)
        self._worker: SnifferWorker | None = None
        self._paused: bool = False
        self._input_active: bool = False

    def compose(self) -> ComposeResult:
        yield RichLog(id="sniffer-log", max_lines=_MAX_LINES, wrap=False, markup=True)
        yield PausedBanner(id="paused-banner")
        yield FilterInput(
            id="filter-input",
            placeholder="e.g. ABCD1234 or 0xABCD1234",
            restrict=r"[0-9A-Fa-fx]*",
        )

    def on_mount(self) -> None:
        self.query_one("#paused-banner", PausedBanner).display = False
        self.query_one("#filter-input", FilterInput).display = False

    def watch_filter_id(self, filter_id: int | None) -> None:
        self.post_message(FilterChanged(filter_id))

    def set_worker(self, worker: SnifferWorker) -> None:
        self._worker = worker

    def action_quit(self) -> None:
        self.app.exit()

    def action_clear(self) -> None:
        self.clear_log()

    def action_toggle_pause(self) -> None:
        self.toggle_pause()

    def clear_log(self) -> None:
        """Clear the log, screen buffer, and (if paused) the worker's pause buffer."""
        log = self.query_one("#sniffer-log", RichLog)
        log.clear()
        self._buffer.clear()
        if self._paused and self._worker is not None:
            self._worker.clear_buffer()
            banner = self.query_one("#paused-banner", PausedBanner)
            banner.queued = 0
            banner.dropped = 0

    def toggle_pause(self) -> None:
        """Pause or resume the sniffer; show/hide the PAUSED banner."""
        if self._worker is None:
            return
        banner = self.query_one("#paused-banner", PausedBanner)
        if not self._paused:
            self._paused = True
            self._worker.pause()
            banner.queued = 0
            banner.dropped = 0
            banner.display = True
        else:
            self._paused = False
            self._worker.resume()
            banner.display = False

    def on_pause_buffer_updated(self, message: PauseBufferUpdated) -> None:
        """Reflect current pause buffer size and overflow count in the banner."""
        if not self._paused:
            return
        banner = self.query_one("#paused-banner", PausedBanner)
        banner.queued = message.queued
        banner.dropped = message.dropped

    def on_telegram_received(self, message: TelegramReceived) -> None:
        """Format incoming telegram, apply live filter, append to buffer and log."""
        ft = format_telegram(message.telegram)
        if self.filter_id is not None and ft.sender_int != self.filter_id:
            return
        self._buffer.append(ft)
        if not self._input_active:
            self.query_one("#sniffer-log", RichLog).write(ft.line)

    def on_parse_warning(self, message: ParseWarning) -> None:
        """Write a yellow warning line for per-telegram parse errors; never crash."""
        safe_msg = markup_escape(str(message.exc))
        self.query_one("#sniffer-log", RichLog).write(f"[yellow]WARNING: {safe_msg}[/yellow]")

    async def on_key(self, event: Key) -> None:
        """Intercept keys for filter input.

        SnifferScreen is embedded as a widget (not pushed as a screen), so
        FilterInput cannot receive focus via the App's focus system. Key events
        from the actually-focused widget (RichLog) bubble up here instead.
        Escape clears an active filter even after it has been applied.
        """
        fi = self.query_one("#filter-input", FilterInput)
        if event.key == "escape" and (self._input_active or self.filter_id is not None):
            event.stop()
            await self._dismiss_filter_input()
            return
        if not self._input_active:
            return
        event.stop()
        if event.key == "enter":
            await self._submit_filter_input(fi)
        elif event.character and re.match(r"[0-9A-Fa-fx]", event.character):
            fi.value += event.character
        elif event.key == "backspace":
            fi.value = fi.value[:-1]

    async def _submit_filter_input(self, fi: FilterInput) -> None:
        raw = fi.value.strip()
        hex_str = raw[2:] if raw.lower().startswith("0x") else raw
        if not hex_str or len(hex_str) > 8:
            fi.value = ""
            return
        try:
            filter_val = int(hex_str, 16)
        except ValueError:
            fi.value = ""
            return
        fi.remove_class("pending")
        fi.display = False
        self._input_active = False
        await self.apply_filter(filter_val)
        self.post_message(FilterChanged(filter_val))

    def toggle_filter_input(self) -> None:
        """Show or hide the FilterInput (called by App on `f` key)."""
        fi = self.query_one("#filter-input", FilterInput)
        if fi.display:
            self.run_worker(self._dismiss_filter_input(), name="dismiss-filter", exclusive=True)
        else:
            fi.value = ""
            fi.add_class("pending")
            fi.display = True
            self._input_active = True

    async def _dismiss_filter_input(self) -> None:
        fi = self.query_one("#filter-input", FilterInput)
        fi.remove_class("pending")
        fi.display = False
        self._input_active = False
        await self.apply_filter(None)
        self.post_message(FilterChanged(None))

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
