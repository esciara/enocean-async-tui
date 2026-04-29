"""Shared `Dongle` protocol, state enum and event dataclasses."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from enocean_async.gateway import SendResult
from enocean_async.protocol.esp3.packet import ESP3Packet

from enocean_async_tui.dongle.types import RawTelegram


class State(StrEnum):
    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class StateChange:
    old: State
    new: State
    at: datetime


@dataclass(frozen=True, slots=True)
class QueueOverflowWarning:
    dropped_count: int
    since: datetime


@runtime_checkable
class Dongle(Protocol):
    """Surface shared by :class:`DongleService` and :class:`FakeDongle`."""

    @property
    def state(self) -> State: ...

    async def connect(self) -> None: ...

    async def aclose(self) -> None: ...

    async def send(self, packet: ESP3Packet) -> SendResult: ...

    def telegrams(self) -> AsyncIterator[RawTelegram]: ...

    def state_changes(self) -> AsyncIterator[StateChange]: ...

    def warnings(self) -> AsyncIterator[QueueOverflowWarning]: ...
