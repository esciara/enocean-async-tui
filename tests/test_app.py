from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from enocean_async_tui.app import EnoceanTuiApp, StatusHeader
from enocean_async_tui.dongle import (
    FakeDongle,
    QueueOverflowWarning,
    RawTelegram,
    State,
    StateChange,
)
from enocean_async_tui.settings import Settings


def _settings() -> Settings:
    return Settings(port="/dev/null", log_level="INFO")


async def test_app_starts_with_fake_shows_connected_fake_mode() -> None:
    fake = FakeDongle()
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: fake)
    async with app.run_test() as pilot:
        # Wait for state to settle.
        for _ in range(20):
            header = pilot.app.query_one("#status-header", StatusHeader)
            if header.status is State.CONNECTED and header.fake_mode:
                break
            await pilot.pause()
        header = pilot.app.query_one("#status-header", StatusHeader)
        assert header.status is State.CONNECTED
        assert header.fake_mode is True


async def test_app_reconnecting_status_after_simulate_disconnect() -> None:
    fake = FakeDongle()
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: fake)
    async with app.run_test() as pilot:
        for _ in range(20):
            if pilot.app.query_one("#status-header", StatusHeader).status is State.CONNECTED:
                break
            await pilot.pause()
        await fake.simulate_disconnect()
        seen_reconnecting = False
        for _ in range(40):
            await pilot.pause()
            status = pilot.app.query_one("#status-header", StatusHeader).status
            if status is State.RECONNECTING:
                seen_reconnecting = True
                break
        assert seen_reconnecting


async def test_quit_key_exits_and_closes_dongle() -> None:
    fake = FakeDongle()
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: fake)
    async with app.run_test() as pilot:
        for _ in range(20):
            if pilot.app.query_one("#status-header", StatusHeader).status is State.CONNECTED:
                break
            await pilot.pause()
        await pilot.press("q")
        await pilot.pause()
    assert fake.state is State.CLOSED


class _RaisingDongle:
    """Stub `Dongle` that raises ConnectionError on connect()."""

    def __init__(self) -> None:
        self.connect_called = 0
        self.aclose_called = 0
        self._state = State.IDLE

    @property
    def state(self) -> State:
        return self._state

    async def connect(self) -> None:
        self.connect_called += 1
        raise ConnectionError("no port")

    async def aclose(self) -> None:
        self.aclose_called += 1
        self._state = State.CLOSED

    async def send(self, packet: object) -> object:  # pragma: no cover - unused
        raise ConnectionError("not connected")

    def telegrams(self) -> AsyncIterator[RawTelegram]:  # pragma: no cover - unused
        return _empty_telegrams()

    def state_changes(self) -> AsyncIterator[StateChange]:  # pragma: no cover - unused
        return _empty_state_changes()

    def warnings(self) -> AsyncIterator[QueueOverflowWarning]:  # pragma: no cover - unused
        return _empty_warnings()


async def _empty_telegrams() -> AsyncIterator[RawTelegram]:  # pragma: no cover
    return
    yield  # pragma: no cover


async def _empty_state_changes() -> AsyncIterator[StateChange]:  # pragma: no cover
    return
    yield  # pragma: no cover


async def _empty_warnings() -> AsyncIterator[QueueOverflowWarning]:  # pragma: no cover
    return
    yield  # pragma: no cover


async def test_modal_appears_when_real_dongle_fails() -> None:
    raising = _RaisingDongle()
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: raising)

    async def _drive() -> None:
        async with app.run_test() as pilot:
            # Wait for modal.
            for _ in range(40):
                await pilot.pause()
                if app.screen.__class__.__name__ == "FallbackModal":
                    return
            pytest.fail("FallbackModal never appeared")

    await _drive()


async def test_modal_quit_exits_app() -> None:
    raising = _RaisingDongle()
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: raising)
    async with app.run_test() as pilot:
        for _ in range(40):
            await pilot.pause()
            if app.screen.__class__.__name__ == "FallbackModal":
                break
        await pilot.click("#modal-quit")
        for _ in range(20):
            await pilot.pause()
            if app.return_code is not None:
                break
    assert app.return_code == 2


async def test_modal_continue_with_fake() -> None:
    raising = _RaisingDongle()
    app = EnoceanTuiApp(_settings(), dongle_factory=lambda: raising)
    async with app.run_test() as pilot:
        for _ in range(40):
            await pilot.pause()
            if app.screen.__class__.__name__ == "FallbackModal":
                break
        await pilot.click("#modal-fake")
        for _ in range(40):
            await pilot.pause()
            header = pilot.app.query_one("#status-header", StatusHeader)
            if header.fake_mode and header.status is State.CONNECTED:
                break
        header = pilot.app.query_one("#status-header", StatusHeader)
        assert header.fake_mode
        assert header.status is State.CONNECTED
