from __future__ import annotations

from pathlib import Path

import pytest

from enocean_async_tui.dongle.fake import FakeDongle, FixtureValidationError


@pytest.mark.parametrize(
    "line,match",
    [
        # missing telegram_hex
        ('{"t_offset_ms": 0, "rssi_dbm": -60}', "telegram_hex"),
        # missing t_offset_ms
        ('{"telegram_hex": "f600aabbcc0130", "rssi_dbm": -60}', "t_offset_ms"),
        # missing rssi_dbm
        ('{"telegram_hex": "f600aabbcc0130", "t_offset_ms": 0}', "rssi_dbm"),
        # wrong type: telegram_hex not str
        ('{"telegram_hex": 123, "t_offset_ms": 0, "rssi_dbm": -60}', "telegram_hex"),
        # wrong type: t_offset_ms not int
        ('{"telegram_hex": "f600aabbcc0130", "t_offset_ms": "0", "rssi_dbm": -60}', "t_offset_ms"),
        # wrong type: rssi_dbm not int or null
        ('{"telegram_hex": "f600aabbcc0130", "t_offset_ms": 0, "rssi_dbm": "-60"}', "rssi_dbm"),
    ],
)
async def test_fixture_validation_malformed(tmp_path: Path, line: str, match: str) -> None:
    fixture = tmp_path / "bad.jsonl"
    fixture.write_text(line + "\n", encoding="utf-8")
    fake = FakeDongle(recording=fixture)
    with pytest.raises(FixtureValidationError, match=match):
        await fake.connect()
