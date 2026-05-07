"""Integration tests for App + SnifferScreen + SnifferWorker wiring (eat-342)."""

from __future__ import annotations

from datetime import UTC, datetime

from enocean_async.address import EURID
from enocean_async.protocol.erp1.rorg import RORG
from enocean_async.protocol.erp1.telegram import ERP1Telegram

from enocean_async_tui.app import EnoceanTuiApp
from enocean_async_tui.dongle.fake import FAKE_RECONNECT_DELAY_S, FakeDongle
from enocean_async_tui.dongle.protocol import State
from enocean_async_tui.dongle.types import RawTelegram
from enocean_async_tui.settings import DEFAULT_MAX_LINES, Settings
from enocean_async_tui.ui.screens.sniffer import SnifferScreen


def _settings() -> Settings:
    return Settings(port="/dev/null", log_level="INFO", fake=False, max_lines=DEFAULT_MAX_LINES)


def _make_raw(sender: int) -> RawTelegram:
    telegram = ERP1Telegram(
        rorg=RORG.RORG_RPS,
        telegram_data=bytes([0x10]),
        sender=EURID(sender),
        status=0x30,
        rssi=200,
    )
    return RawTelegram(raw=telegram, received_at=datetime.now(tz=UTC))


async def _wait_connected(fake: FakeDongle, pilot: object) -> None:
    for _ in range(40):
        await pilot.pause()  # type: ignore[attr-defined]
        if fake.state is State.CONNECTED:
            return
    raise TimeoutError("FakeDongle never reached CONNECTED")


async def test_live_display() -> None:
    """3 telegrams pushed to FakeDongle → all 3 appear in SnifferScreen._buffer."""
    fake = FakeDongle(queue_size=1000)
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: fake)

    async with app.run_test() as pilot:
        await _wait_connected(fake, pilot)

        # Give workers time to start
        for _ in range(10):
            await pilot.pause()

        senders = [0x11110001, 0x22220002, 0x33330003]
        for sender in senders:
            await fake.push_raw(_make_raw(sender))

        # Wait for all 3 to appear in SnifferScreen buffer
        screen = app.query_one(SnifferScreen)
        for _ in range(40):
            await pilot.pause()
            if len(screen._buffer) >= 3:  # noqa: SLF001
                break

        assert len(screen._buffer) == 3  # noqa: SLF001
        buffered_senders = [int(ft.raw.sender) for ft in screen._buffer]  # noqa: SLF001
        assert buffered_senders == senders


async def test_reconnect_streaming() -> None:
    """2 telegrams + disconnect + reconnect + 2 more → all 4 in SnifferScreen._buffer."""
    fake = FakeDongle(queue_size=1000)
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: fake)

    async with app.run_test() as pilot:
        await _wait_connected(fake, pilot)

        for _ in range(10):
            await pilot.pause()

        screen = app.query_one(SnifferScreen)

        # Stream 2 telegrams before disconnect
        await fake.push_raw(_make_raw(0xAAAA0001))
        await fake.push_raw(_make_raw(0xAAAA0002))

        for _ in range(40):
            await pilot.pause()
            if len(screen._buffer) >= 2:  # noqa: SLF001
                break

        assert len(screen._buffer) == 2  # noqa: SLF001

        # Simulate disconnect; FakeDongle auto-reconnects after FAKE_RECONNECT_DELAY_S
        await fake.simulate_disconnect()

        # Wait for reconnect
        for _ in range(int(FAKE_RECONNECT_DELAY_S * 200) + 40):
            await pilot.pause()
            if fake.state is State.CONNECTED:
                break

        assert fake.state is State.CONNECTED, "FakeDongle never reconnected"

        # Give worker time to re-enter streaming loop
        for _ in range(20):
            await pilot.pause()

        # Stream 2 more telegrams after reconnect
        await fake.push_raw(_make_raw(0xBBBB0003))
        await fake.push_raw(_make_raw(0xBBBB0004))

        for _ in range(40):
            await pilot.pause()
            if len(screen._buffer) >= 4:  # noqa: SLF001
                break

        # All 4 must be present — no hang after reconnect
        assert len(screen._buffer) == 4  # noqa: SLF001
