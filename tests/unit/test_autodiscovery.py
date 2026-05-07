"""Auto-discovery unit tests — eat-mh6 acceptance criteria."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import serial.tools.list_ports

from enocean_async_tui.app import EnoceanTuiApp, StatusHeader
from enocean_async_tui.dongle import FakeDongle, State
from enocean_async_tui.dongle.autodiscovery import ENOCEAN_VID_PIDS, discover_dongles
from enocean_async_tui.settings import Settings


def _autodiscover_settings() -> Settings:
    return Settings(port=None, log_level="INFO", fake=False, max_lines=10_000)


async def test_autodiscovery_uses_to_thread() -> None:
    """comports() is called via asyncio.to_thread, never directly on the event loop."""
    with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
        mock_to_thread.return_value = []
        result = await discover_dongles()

    mock_to_thread.assert_called_once_with(serial.tools.list_ports.comports)
    assert result == []


async def test_autodiscovery_single_dongle() -> None:
    """When exactly one EnOcean dongle is found, auto-connect without showing any modal."""
    fake = FakeDongle()

    with (
        patch("enocean_async_tui.app.discover_dongles", new_callable=AsyncMock, return_value=["/dev/ttyUSB0"]),
        patch("enocean_async_tui.app.DongleService", return_value=fake),
    ):
        app = EnoceanTuiApp(_autodiscover_settings())
        async with app.run_test() as pilot:
            for _ in range(40):
                await pilot.pause()
                header = pilot.app.query_one("#status-header", StatusHeader)
                if header.status is State.CONNECTED:
                    break
            header = pilot.app.query_one("#status-header", StatusHeader)
            assert header.status is State.CONNECTED
            assert app.screen.__class__.__name__ not in {"FallbackModal", "DongleSelectionModal"}


async def test_autodiscovery_multiple_dongles() -> None:
    """When multiple EnOcean dongles are found, the DongleSelectionModal is shown."""
    with patch(
        "enocean_async_tui.app.discover_dongles",
        new_callable=AsyncMock,
        return_value=["/dev/ttyUSB0", "/dev/ttyACM0"],
    ):
        app = EnoceanTuiApp(_autodiscover_settings())
        async with app.run_test() as pilot:
            for _ in range(40):
                await pilot.pause()
                if app.screen.__class__.__name__ == "DongleSelectionModal":
                    return
            pytest.fail("DongleSelectionModal never appeared")


async def test_autodiscovery_no_dongle() -> None:
    """When no EnOcean dongle is found, the FallbackModal is shown."""
    with patch("enocean_async_tui.app.discover_dongles", new_callable=AsyncMock, return_value=[]):
        app = EnoceanTuiApp(_autodiscover_settings())
        async with app.run_test() as pilot:
            for _ in range(40):
                await pilot.pause()
                if app.screen.__class__.__name__ == "FallbackModal":
                    return
            pytest.fail("FallbackModal never appeared")


def test_enocean_vid_pids_nonempty() -> None:
    """ENOCEAN_VID_PIDS contains at least one known VID/PID pair."""
    assert len(ENOCEAN_VID_PIDS) > 0
    for vid, pid in ENOCEAN_VID_PIDS:
        assert isinstance(vid, int)
        assert isinstance(pid, int)


async def test_autodiscovery_filters_non_enocean_ports() -> None:
    """Ports whose VID/PID don't match any known EnOcean dongle are excluded."""
    non_enocean = MagicMock()
    non_enocean.device = "/dev/ttyS0"
    non_enocean.vid = 0x1234
    non_enocean.pid = 0x5678

    with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
        mock_to_thread.return_value = [non_enocean]
        result = await discover_dongles()

    assert result == []


async def test_autodiscovery_includes_matching_ports() -> None:
    """Ports whose VID/PID match a known EnOcean dongle are included."""
    vid, pid = next(iter(ENOCEAN_VID_PIDS))
    matching = MagicMock()
    matching.device = "/dev/ttyUSB0"
    matching.vid = vid
    matching.pid = pid

    with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
        mock_to_thread.return_value = [matching]
        result = await discover_dongles()

    assert result == ["/dev/ttyUSB0"]
