"""Integration tests for App + SnifferScreen + SnifferWorker wiring (eat-342)."""

from __future__ import annotations

from datetime import UTC, datetime

from enocean_async.address import EURID
from enocean_async.protocol.erp1.rorg import RORG
from enocean_async.protocol.erp1.telegram import ERP1Telegram
from textual.widgets import RichLog

from enocean_async_tui.app import EnoceanTuiApp, StatusHeader
from enocean_async_tui.dongle.fake import FAKE_RECONNECT_DELAY_S, FakeDongle
from enocean_async_tui.dongle.protocol import State
from enocean_async_tui.dongle.types import RawTelegram
from enocean_async_tui.settings import DEFAULT_MAX_LINES, Settings
from enocean_async_tui.ui.screens.sniffer import FilterInput, PausedBanner, SnifferScreen


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

        for _ in range(10):
            await pilot.pause()

        senders = [0x11110001, 0x22220002, 0x33330003]
        for sender in senders:
            await fake.push_raw(_make_raw(sender))

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

        await fake.push_raw(_make_raw(0xAAAA0001))
        await fake.push_raw(_make_raw(0xAAAA0002))

        for _ in range(40):
            await pilot.pause()
            if len(screen._buffer) >= 2:  # noqa: SLF001
                break

        assert len(screen._buffer) == 2  # noqa: SLF001

        await fake.simulate_disconnect()

        for _ in range(int(FAKE_RECONNECT_DELAY_S * 200) + 40):
            await pilot.pause()
            if fake.state is State.CONNECTED:
                break

        assert fake.state is State.CONNECTED, "FakeDongle never reconnected"

        for _ in range(20):
            await pilot.pause()

        await fake.push_raw(_make_raw(0xBBBB0003))
        await fake.push_raw(_make_raw(0xBBBB0004))

        for _ in range(40):
            await pilot.pause()
            if len(screen._buffer) >= 4:  # noqa: SLF001
                break

        assert len(screen._buffer) == 4  # noqa: SLF001


# ---------------------------------------------------------------------------
# Pause tests (eat-1bn)
# ---------------------------------------------------------------------------


async def test_pause_resume() -> None:
    """2 before pause, 2 more after, resume → 4 total; none lost (eat-1bn)."""
    fake = FakeDongle(queue_size=1000)
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: fake)

    async with app.run_test() as pilot:
        await _wait_connected(fake, pilot)
        for _ in range(10):
            await pilot.pause()

        screen = app.query_one(SnifferScreen)

        await fake.push_raw(_make_raw(0x11110001))
        await fake.push_raw(_make_raw(0x22220002))
        for _ in range(40):
            await pilot.pause()
            if len(screen._buffer) >= 2:  # noqa: SLF001
                break
        assert len(screen._buffer) == 2  # noqa: SLF001

        await pilot.press("p")
        for _ in range(10):
            await pilot.pause()
        assert screen._paused is True  # noqa: SLF001

        await fake.push_raw(_make_raw(0x33330003))
        await fake.push_raw(_make_raw(0x44440004))
        assert screen._worker is not None  # noqa: SLF001
        for _ in range(40):
            await pilot.pause()
            if len(screen._worker._pause_buffer) >= 2:  # noqa: SLF001
                break
        assert len(screen._worker._pause_buffer) == 2  # noqa: SLF001
        assert len(screen._buffer) == 2  # noqa: SLF001

        await pilot.press("p")
        for _ in range(40):
            await pilot.pause()
            if len(screen._buffer) >= 4:  # noqa: SLF001
                break
        assert len(screen._buffer) == 4  # noqa: SLF001


async def test_pause_overflow() -> None:
    """Pause + 257 telegrams → 256 buffered; dropped counter = 1 (eat-1bn)."""
    fake = FakeDongle(queue_size=1000)
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: fake)

    async with app.run_test() as pilot:
        await _wait_connected(fake, pilot)
        for _ in range(10):
            await pilot.pause()

        screen = app.query_one(SnifferScreen)

        await pilot.press("p")
        for _ in range(10):
            await pilot.pause()
        assert screen._paused is True  # noqa: SLF001

        for i in range(257):
            await fake.push_raw(_make_raw(0x10000000 + i))

        assert screen._worker is not None  # noqa: SLF001
        for _ in range(80):
            await pilot.pause()
            if screen._worker._dropped_count >= 1:  # noqa: SLF001
                break

        assert len(screen._worker._pause_buffer) == 256  # noqa: SLF001
        assert screen._worker._dropped_count == 1  # noqa: SLF001


async def test_pause_banner() -> None:
    """Banner shows 'PAUSED — N queued'; '1 dropped' after overflow (eat-1bn)."""
    fake = FakeDongle(queue_size=1000)
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: fake)

    async with app.run_test() as pilot:
        await _wait_connected(fake, pilot)
        for _ in range(10):
            await pilot.pause()

        screen = app.query_one(SnifferScreen)
        banner = screen.query_one("#paused-banner", PausedBanner)

        assert banner.display is False

        await pilot.press("p")
        for _ in range(10):
            await pilot.pause()

        assert banner.display is True
        assert banner.queued == 0

        for i in range(257):
            await fake.push_raw(_make_raw(0x10000000 + i))

        assert screen._worker is not None  # noqa: SLF001
        for _ in range(80):
            await pilot.pause()
            if banner.dropped >= 1:
                break

        assert banner.queued == 256
        assert banner.dropped == 1


async def test_clear_running() -> None:
    """Press c while running → log buffer empty (eat-1bn)."""
    fake = FakeDongle(queue_size=1000)
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: fake)

    async with app.run_test() as pilot:
        await _wait_connected(fake, pilot)
        for _ in range(10):
            await pilot.pause()

        screen = app.query_one(SnifferScreen)

        for sender in [0x11110001, 0x22220002, 0x33330003]:
            await fake.push_raw(_make_raw(sender))
        for _ in range(40):
            await pilot.pause()
            if len(screen._buffer) >= 3:  # noqa: SLF001
                break
        assert len(screen._buffer) == 3  # noqa: SLF001

        await pilot.press("c")
        for _ in range(10):
            await pilot.pause()

        assert len(screen._buffer) == 0  # noqa: SLF001


async def test_clear_paused() -> None:
    """Clear while paused → log empty after resume (eat-1bn)."""
    fake = FakeDongle(queue_size=1000)
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: fake)

    async with app.run_test() as pilot:
        await _wait_connected(fake, pilot)
        for _ in range(10):
            await pilot.pause()

        screen = app.query_one(SnifferScreen)

        await fake.push_raw(_make_raw(0x11110001))
        for _ in range(40):
            await pilot.pause()
            if len(screen._buffer) >= 1:  # noqa: SLF001
                break

        await pilot.press("p")
        for _ in range(10):
            await pilot.pause()

        for i in range(5):
            await fake.push_raw(_make_raw(0x20000000 + i))
        assert screen._worker is not None  # noqa: SLF001
        for _ in range(40):
            await pilot.pause()
            if len(screen._worker._pause_buffer) >= 5:  # noqa: SLF001
                break

        await pilot.press("c")
        for _ in range(10):
            await pilot.pause()

        await pilot.press("p")
        for _ in range(20):
            await pilot.pause()

        assert len(screen._buffer) == 0  # noqa: SLF001


async def test_quit_binding() -> None:
    """Press q → app exits cleanly (eat-1bn)."""
    fake = FakeDongle(queue_size=1000)
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: fake)

    async with app.run_test() as pilot:
        await _wait_connected(fake, pilot)
        for _ in range(5):
            await pilot.pause()
        await pilot.press("q")

    assert app.return_code in (None, 0)


# ---------------------------------------------------------------------------
# Filter tests (eat-1jh)
# ---------------------------------------------------------------------------

ID_A = 0xAAAA0001
ID_B = 0xBBBB0002
ID_A_HEX = "AAAA0001"
ID_A_DISPLAY = "0xAAAA0001"


async def _push_and_wait(fake: FakeDongle, pilot: object, screen: SnifferScreen, count: int) -> None:
    for _ in range(40):
        await pilot.pause()  # type: ignore[attr-defined]
        if len(screen._buffer) >= count:  # noqa: SLF001
            return
    raise TimeoutError(f"Expected {count} entries in buffer, got {len(screen._buffer)}")  # noqa: SLF001


async def _type(pilot: object, text: str) -> None:
    """Press each character individually (Pilot.type not available in this version)."""
    for ch in text:
        await pilot.press(ch)  # type: ignore[attr-defined]


async def test_filter_retroactive() -> None:
    """Replay 2×ID-A + 2×ID-B, press f, type ID-A hex, Enter → only 2 ID-A lines visible."""
    fake = FakeDongle(queue_size=1000)
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: fake)

    async with app.run_test() as pilot:
        await _wait_connected(fake, pilot)
        for _ in range(10):
            await pilot.pause()

        screen = app.query_one(SnifferScreen)

        for _ in range(2):
            await fake.push_raw(_make_raw(ID_A))
        for _ in range(2):
            await fake.push_raw(_make_raw(ID_B))
        await _push_and_wait(fake, pilot, screen, 4)

        await pilot.press("f")
        for _ in range(5):
            await pilot.pause()

        fi = screen.query_one("#filter-input", FilterInput)
        assert fi.display, "FilterInput should be visible after pressing f"

        await _type(pilot, ID_A_HEX)
        await pilot.press("enter")
        for _ in range(20):
            await pilot.pause()

        log = screen.query_one("#sniffer-log", RichLog)
        assert screen.filter_id == ID_A  # noqa: SLF001
        assert len(log.lines) == 2


async def test_filter_live() -> None:
    """Set filter for ID-A, then push ID-A + ID-B → only ID-A entries in buffer."""
    fake = FakeDongle(queue_size=1000)
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: fake)

    async with app.run_test() as pilot:
        await _wait_connected(fake, pilot)
        for _ in range(10):
            await pilot.pause()

        screen = app.query_one(SnifferScreen)

        await pilot.press("f")
        for _ in range(5):
            await pilot.pause()
        await _type(pilot, ID_A_HEX)
        await pilot.press("enter")
        for _ in range(10):
            await pilot.pause()

        assert screen.filter_id == ID_A  # noqa: SLF001

        await fake.push_raw(_make_raw(ID_A))
        await fake.push_raw(_make_raw(ID_A))
        await fake.push_raw(_make_raw(ID_B))

        for _ in range(40):
            await pilot.pause()
            if len(screen._buffer) >= 2:  # noqa: SLF001
                break

        assert len(screen._buffer) == 2  # noqa: SLF001
        assert all(ft.sender_int == ID_A for ft in screen._buffer)  # noqa: SLF001


async def test_filter_enter() -> None:
    """Pressing f adds pending CSS; log unchanged while typing; updates only on Enter."""
    fake = FakeDongle(queue_size=1000)
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: fake)

    async with app.run_test() as pilot:
        await _wait_connected(fake, pilot)
        for _ in range(10):
            await pilot.pause()

        screen = app.query_one(SnifferScreen)

        await pilot.press("f")
        for _ in range(5):
            await pilot.pause()

        fi = screen.query_one("#filter-input", FilterInput)
        assert fi.display
        assert fi.has_class("pending"), "FilterInput should have 'pending' CSS class while open"

        await fake.push_raw(_make_raw(ID_A))
        for _ in range(20):
            await pilot.pause()

        log = screen.query_one("#sniffer-log", RichLog)
        assert len(log.lines) == 0, "Log should not update while filter input is open"

        await _type(pilot, ID_A_HEX)
        await pilot.press("enter")
        for _ in range(20):
            await pilot.pause()

        assert not fi.has_class("pending"), "pending CSS class should be removed after Enter"
        assert len(log.lines) == 1
        assert not fi.display, "FilterInput should be hidden after Enter"


async def test_filter_clear() -> None:
    """Apply filter, press Escape → filter_id reset, full log re-renders."""
    fake = FakeDongle(queue_size=1000)
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: fake)

    async with app.run_test() as pilot:
        await _wait_connected(fake, pilot)
        for _ in range(10):
            await pilot.pause()

        screen = app.query_one(SnifferScreen)

        for _ in range(2):
            await fake.push_raw(_make_raw(ID_A))
        for _ in range(2):
            await fake.push_raw(_make_raw(ID_B))
        await _push_and_wait(fake, pilot, screen, 4)

        await pilot.press("f")
        for _ in range(5):
            await pilot.pause()
        await _type(pilot, ID_A_HEX)
        await pilot.press("enter")
        for _ in range(20):
            await pilot.pause()

        log = screen.query_one("#sniffer-log", RichLog)
        assert len(log.lines) == 2

        await pilot.press("escape")
        for _ in range(20):
            await pilot.pause()

        assert screen.filter_id is None  # noqa: SLF001
        assert len(log.lines) == 4, "Full log should re-render after clearing filter"


async def test_filter_empty_notice() -> None:
    """Filter matching zero buffer entries → empty-filter notice shown in RichLog."""
    fake = FakeDongle(queue_size=1000)
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: fake)

    async with app.run_test() as pilot:
        await _wait_connected(fake, pilot)
        for _ in range(10):
            await pilot.pause()

        screen = app.query_one(SnifferScreen)
        await fake.push_raw(_make_raw(ID_A))
        await _push_and_wait(fake, pilot, screen, 1)

        await pilot.press("f")
        for _ in range(5):
            await pilot.pause()
        await _type(pilot, "CCCC0003")
        await pilot.press("enter")
        for _ in range(20):
            await pilot.pause()

        log = screen.query_one("#sniffer-log", RichLog)
        assert len(log.lines) == 1, "Empty-filter notice should occupy exactly one line"


async def test_filter_active_indicator() -> None:
    """StatusHeader shows filter indicator while filter is active; clears on Escape."""
    fake = FakeDongle(queue_size=1000)
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: fake)

    async with app.run_test() as pilot:
        await _wait_connected(fake, pilot)
        for _ in range(10):
            await pilot.pause()

        screen = app.query_one(SnifferScreen)
        await fake.push_raw(_make_raw(ID_A))
        await _push_and_wait(fake, pilot, screen, 1)

        await pilot.press("f")
        for _ in range(5):
            await pilot.pause()
        await _type(pilot, ID_A_HEX)
        await pilot.press("enter")
        for _ in range(10):
            await pilot.pause()

        header = app.query_one("#status-header", StatusHeader)
        assert ID_A_DISPLAY in header.render(), f"Header should show {ID_A_DISPLAY} while filter active"

        await pilot.press("escape")
        for _ in range(10):
            await pilot.pause()
        assert ID_A_DISPLAY not in header.render(), "Header should not show filter after clearing"
