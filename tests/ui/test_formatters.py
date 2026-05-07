from __future__ import annotations

import re
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from enocean_async.address import EURID, BaseAddress
from enocean_async.protocol.erp1.rorg import RORG
from enocean_async.protocol.erp1.telegram import ERP1Telegram

from enocean_async_tui.dongle.types import RawTelegram
from enocean_async_tui.ui.formatters import FormattedTelegram, format_telegram

_FIXED_DT = datetime(2026, 5, 7, 14, 23, 1, 42000)
_FIXED_TS = "2026-05-07T14:23:01.042"


def _make_raw(
    *,
    rorg: RORG = RORG.RORG_RPS,
    data: bytes = bytes([0x10]),
    sender: EURID | BaseAddress | None = None,
    rssi: int | None = 200,
) -> RawTelegram:
    if sender is None:
        sender = EURID(0xABCD1234)
    telegram = ERP1Telegram(
        rorg=rorg,
        telegram_data=data,
        sender=sender,
        status=0x30,
        rssi=rssi,
    )
    return RawTelegram(raw=telegram, received_at=datetime.now(tz=UTC))


def test_format_telegram() -> None:
    raw = _make_raw(data=bytes([0xAB, 0xCD]), sender=EURID(0xABCD1234), rssi=200)
    with patch("enocean_async_tui.ui.formatters.datetime") as mock_dt:
        mock_dt.now.return_value = _FIXED_DT
        ft = format_telegram(raw)

    assert ft.timestamp == _FIXED_TS
    assert ft.sender_id == "0xABCD1234"
    assert ft.sender_int == 0xABCD1234
    assert ft.rorg_name == "RPS (0xF6)"
    assert ft.payload_hex == "ABCD"
    assert ft.rssi_dbm == 200
    assert isinstance(ft.raw, RawTelegram)

    expected_line = (
        f"[dim]{_FIXED_TS}[/dim]  "
        "[cyan bold]0xABCD1234[/cyan bold]  "
        "[yellow]RPS (0xF6)[/yellow]  "
        "ABCD  "
        "[blue]RSSI 200 dBm[/blue]"
    )
    assert ft.line == expected_line


def test_format_telegram_rssi_none() -> None:
    raw = _make_raw(rssi=0xFF)  # 0xFF → rssi_dbm is None per RawTelegram
    with patch("enocean_async_tui.ui.formatters.datetime") as mock_dt:
        mock_dt.now.return_value = _FIXED_DT
        ft = format_telegram(raw)

    assert ft.rssi_dbm is None
    assert "[blue]RSSI N/A[/blue]" in ft.line


def test_format_telegram_sender_int() -> None:
    raw = _make_raw(sender=EURID(0x01234567))
    ft = format_telegram(raw)
    assert ft.sender_int == int(raw.sender)
    assert ft.sender_int == 0x01234567


def test_format_telegram_sender_int_base_address() -> None:
    raw = _make_raw(sender=BaseAddress(0xFF800001))
    ft = format_telegram(raw)
    assert ft.sender_int == int(raw.sender)
    assert ft.sender_int == 0xFF800001
    assert ft.sender_id == "0xFF800001"


@pytest.mark.parametrize(
    ("rorg", "expected_name"),
    [
        (RORG.RORG_RPS, "RPS (0xF6)"),
        (RORG.RORG_1BS, "1BS (0xD5)"),
        (RORG.RORG_4BS, "4BS (0xA5)"),
        (RORG.RORG_VLD, "VLD (0xD2)"),
        (RORG.RORG_UTE, "UTE (0xD4)"),
        (RORG.RORG_MSC, "MSC (0xD1)"),
        (RORG.RORG_ADT_VLD, "ADT_VLD (0xA6)"),
    ],
)
def test_rorg_lookup(rorg: RORG, expected_name: str) -> None:
    data_map = {
        RORG.RORG_RPS: bytes([0x10]),
        RORG.RORG_1BS: bytes([0x08]),
        RORG.RORG_4BS: bytes([0x00, 0x00, 0x00, 0x08]),
        RORG.RORG_VLD: bytes([0x01]),
        RORG.RORG_UTE: b"\xd1\x41\x02\x01\x00\xff\xff\xff",
        RORG.RORG_MSC: bytes([0x01]),
        RORG.RORG_ADT_VLD: bytes([0x01]),
    }
    raw = _make_raw(rorg=rorg, data=data_map[rorg])
    ft = format_telegram(raw)
    assert ft.rorg_name == expected_name


def test_format_telegram_line_format_pattern() -> None:
    raw = _make_raw()
    ft = format_telegram(raw)
    ts_pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}"
    pattern = (
        rf"^\[dim\]{ts_pattern}\[/dim\]  "
        r"\[cyan bold\]0x[0-9A-F]{8}\[/cyan bold\]  "
        r"\[yellow\].+\[/yellow\]  "
        r"[0-9A-F]+  "
        r"\[blue\]RSSI .+\[/blue\]$"
    )
    assert re.match(pattern, ft.line), f"Line did not match pattern: {ft.line!r}"


def test_returned_type_is_frozen_dataclass() -> None:
    raw = _make_raw()
    ft = format_telegram(raw)
    assert isinstance(ft, FormattedTelegram)
    with pytest.raises((AttributeError, TypeError)):
        ft.sender_id = "mutated"  # type: ignore[misc]
