"""Telegram formatting: RawTelegram → FormattedTelegram with precomputed Rich-markup line."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from rich.markup import escape as markup_escape

from enocean_async_tui.dongle.types import RawTelegram


@dataclass(frozen=True, slots=True)
class FormattedTelegram:
    timestamp: str
    sender_id: str
    sender_int: int
    rorg_name: str
    payload_hex: str
    rssi_dbm: int | None
    line: str
    raw: RawTelegram


def format_telegram(t: RawTelegram) -> FormattedTelegram:
    timestamp = datetime.now().isoformat(timespec="milliseconds")
    sender_int = int(t.sender)
    sender_id = f"0x{sender_int:08X}"
    rorg_name = f"{t.rorg.simple_name} (0x{t.rorg.value:02X})"
    payload_hex = t.payload.hex().upper()
    rssi_dbm = t.rssi_dbm

    rssi_str = f"{rssi_dbm} dBm" if rssi_dbm is not None else "N/A"

    line = (
        f"[dim]{markup_escape(timestamp)}[/dim]  "
        f"[cyan bold]{markup_escape(sender_id)}[/cyan bold]  "
        f"[yellow]{markup_escape(rorg_name)}[/yellow]  "
        f"{markup_escape(payload_hex)}  "
        f"[blue]RSSI {markup_escape(rssi_str)}[/blue]"
    )

    return FormattedTelegram(
        timestamp=timestamp,
        sender_id=sender_id,
        sender_int=sender_int,
        rorg_name=rorg_name,
        payload_hex=payload_hex,
        rssi_dbm=rssi_dbm,
        line=line,
        raw=t,
    )
