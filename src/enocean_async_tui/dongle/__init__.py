"""Dongle layer: protocol, types, real service, in-memory fake, and discovery."""

from enocean_async_tui.dongle.autodiscovery import discover_dongles
from enocean_async_tui.dongle.fake import FakeDongle
from enocean_async_tui.dongle.protocol import (
    Dongle,
    QueueOverflowWarning,
    State,
    StateChange,
)
from enocean_async_tui.dongle.service import DongleService
from enocean_async_tui.dongle.types import RawTelegram

__all__ = [
    "Dongle",
    "DongleService",
    "FakeDongle",
    "QueueOverflowWarning",
    "RawTelegram",
    "State",
    "StateChange",
    "discover_dongles",
]
