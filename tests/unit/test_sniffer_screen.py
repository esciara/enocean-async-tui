"""Unit tests for SnifferScreen — eat-09q acceptance criteria."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime

from enocean_async.address import EURID
from enocean_async.protocol.erp1.rorg import RORG
from enocean_async.protocol.erp1.telegram import ERP1Telegram
from textual.app import App, ComposeResult

from enocean_async_tui.dongle.types import RawTelegram
from enocean_async_tui.ui.formatters import FormattedTelegram
from enocean_async_tui.ui.messages import ParseWarning, TelegramReceived
from enocean_async_tui.ui.screens.sniffer import SnifferScreen


def _make_raw(*, sender_int: int = 0xABCD1234) -> RawTelegram:
    telegram = ERP1Telegram(
        rorg=RORG.RORG_RPS,
        telegram_data=bytes([0x10]),
        sender=EURID(sender_int),
        status=0x30,
        rssi=200,
    )
    return RawTelegram(raw=telegram, received_at=datetime.now(tz=UTC))


class _SnifferApp(App[None]):
    def compose(self) -> ComposeResult:
        yield SnifferScreen()


async def test_buffer_maxlen() -> None:
    """_buffer is deque(maxlen=10_000); 10 001st entry drops oldest without raising."""
    app = _SnifferApp()
    async with app.run_test() as pilot:
        screen = pilot.app.query_one(SnifferScreen)
        assert isinstance(screen._buffer, deque)
        assert screen._buffer.maxlen == 10_000

        # Build a minimal FormattedTelegram to append (faster than routing messages)
        raw = _make_raw(sender_int=0)
        dummy_ft = FormattedTelegram(
            timestamp="2026-01-01T00:00:00.000",
            sender_id="0x00000000",
            sender_int=0,
            rorg_name="RPS (0xF6)",
            payload_hex="10",
            rssi_dbm=None,
            line="dummy",
            raw=raw,
        )

        for i in range(10_001):
            ft = FormattedTelegram(
                timestamp="2026-01-01T00:00:00.000",
                sender_id=f"0x{i:08X}",
                sender_int=i,
                rorg_name="RPS (0xF6)",
                payload_hex="10",
                rssi_dbm=None,
                line=f"line {i}",
                raw=dummy_ft.raw,
            )
            screen._buffer.append(ft)

        assert len(screen._buffer) == 10_000
        assert screen._buffer[0].sender_int == 1  # oldest (0) was dropped
        assert screen._buffer[-1].sender_int == 10_000


async def test_filter_sender_int_comparison() -> None:
    """Filter uses entry.sender_int == filter_id (integer comparison, not string)."""
    app = _SnifferApp()
    async with app.run_test() as pilot:
        screen = pilot.app.query_one(SnifferScreen)

        # Set filter before posting messages
        screen.filter_id = 0xAAAAAAAA

        raw_match = _make_raw(sender_int=0xAAAAAAAA)
        raw_no_match = _make_raw(sender_int=0xBBBBBBBB)

        screen.post_message(TelegramReceived(raw_match))
        screen.post_message(TelegramReceived(raw_no_match))
        screen.post_message(TelegramReceived(raw_match))

        # Let messages drain
        for _ in range(10):
            await pilot.pause()

        assert len(screen._buffer) == 2
        assert all(entry.sender_int == 0xAAAAAAAA for entry in screen._buffer)


async def test_parse_error_display() -> None:
    """ParseWarning: yellow warning written to RichLog; no crash; buffer unaffected."""
    app = _SnifferApp()
    async with app.run_test() as pilot:
        screen = pilot.app.query_one(SnifferScreen)

        exc = ValueError("malformed telegram data [bold] injection attempt")
        screen.post_message(ParseWarning(exc))

        for _ in range(10):
            await pilot.pause()

        # No crash; ParseWarning does not go into the telegram buffer
        assert len(screen._buffer) == 0
