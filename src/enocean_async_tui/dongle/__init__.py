"""Dongle layer: protocol, types, real service, and in-memory fake."""

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
]
