"""Public dataclasses for the dongle layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from enocean_async.address import EURID, BaseAddress, BroadcastAddress
from enocean_async.protocol.erp1.rorg import RORG
from enocean_async.protocol.erp1.telegram import ERP1Telegram

# 0xFF in the upstream dataclass means "rssi unknown".
_RSSI_UNKNOWN = 0xFF


@dataclass(frozen=True, slots=True)
class RawTelegram:
    """Wraps an upstream :class:`ERP1Telegram` and adds an arrival timestamp.

    Everything else (sender, RORG, payload, RSSI) is exposed as a passthrough
    property so call sites have a single shape to work with.
    """

    raw: ERP1Telegram
    received_at: datetime

    @property
    def rssi_dbm(self) -> int | None:
        rssi: int | None = self.raw.rssi
        if rssi is None or rssi == _RSSI_UNKNOWN:
            return None
        return rssi

    @property
    def sender(self) -> EURID | BaseAddress:
        sender: EURID | BaseAddress = self.raw.sender
        return sender

    @property
    def rorg(self) -> RORG:
        rorg: RORG = self.raw.rorg
        return rorg

    @property
    def payload(self) -> bytes:
        payload: bytes = self.raw.telegram_data
        return payload

    @property
    def destination(self) -> EURID | BroadcastAddress | None:
        destination: EURID | BroadcastAddress | None = self.raw.destination
        return destination
