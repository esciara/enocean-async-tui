"""Textual message classes for the sniffer UI."""

from __future__ import annotations

from textual.message import Message

from enocean_async_tui.dongle.types import RawTelegram


class TelegramReceived(Message):
    """Delivered by SnifferWorker to SnifferScreen for each received telegram."""

    def __init__(self, telegram: RawTelegram) -> None:
        super().__init__()
        self.telegram: RawTelegram = telegram


class ParseWarning(Message):
    """Posted by SnifferWorker when a per-telegram parse error occurs."""

    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self.exc: Exception = exc


class PauseBufferUpdated(Message):
    """Posted by SnifferWorker each time the pause buffer changes while paused."""

    def __init__(self, queued: int, dropped: int) -> None:
        super().__init__()
        self.queued: int = queued
        self.dropped: int = dropped
