from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from enocean_async.address import EURID
from enocean_async.protocol.erp1.rorg import RORG
from enocean_async.protocol.erp1.telegram import ERP1Telegram

from enocean_async_tui.dongle import (
    FakeDongle,
    QueueOverflowWarning,
    State,
    StateChange,
    _streams,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "recordings"


async def _drain_state_changes(fake: FakeDongle, count: int, timeout: float = 1.0) -> list[StateChange]:
    iterator = fake.state_changes()
    out: list[StateChange] = []
    async with asyncio.timeout(timeout):
        async for change in iterator:
            out.append(change)
            if len(out) >= count:
                break
    return out


async def test_construction_with_no_recording_idle_then_connected() -> None:
    fake = FakeDongle()
    assert fake.state is State.IDLE

    changes_iter = fake.state_changes()
    await fake.connect()
    assert fake.state is State.CONNECTED

    # First two changes: IDLE -> CONNECTING -> CONNECTED.
    seen = []
    async with asyncio.timeout(1.0):
        async for change in changes_iter:
            seen.append(change)
            if len(seen) == 2:
                break
    assert seen[0].old is State.IDLE
    assert seen[0].new is State.CONNECTING
    assert seen[1].old is State.CONNECTING
    assert seen[1].new is State.CONNECTED

    # No telegrams arrive until push() is called — verify by polling for a tiny moment.
    telegrams_iter = fake.telegrams()
    with pytest.raises(asyncio.TimeoutError):
        async with asyncio.timeout(0.05):
            await telegrams_iter.__anext__()

    await fake.aclose()


async def test_push_delivers_telegram() -> None:
    fake = FakeDongle()
    await fake.connect()

    telegram = ERP1Telegram(
        rorg=RORG.RORG_RPS,
        telegram_data=bytes([0x10]),
        sender=EURID(0x01234567),
        status=0x30,
        rssi=200,
    )
    iterator = fake.telegrams()
    await fake.push(telegram)
    async with asyncio.timeout(1.0):
        wrapped = await iterator.__anext__()
    assert wrapped.rssi_dbm == 200
    assert wrapped.payload == bytes([0x10])
    assert wrapped.received_at.tzinfo is not None

    await fake.aclose()


async def test_push_with_rssi_override() -> None:
    fake = FakeDongle()
    await fake.connect()

    telegram = ERP1Telegram(
        rorg=RORG.RORG_RPS,
        telegram_data=bytes([0x10]),
        sender=EURID(0x01234567),
        status=0x30,
    )
    iterator = fake.telegrams()
    await fake.push(telegram, rssi_dbm=-70)
    async with asyncio.timeout(1.0):
        wrapped = await iterator.__anext__()
    assert wrapped.rssi_dbm == -70
    await fake.aclose()


async def test_recording_replay_single_rps() -> None:
    fake = FakeDongle(recording=FIXTURES / "single-rps.jsonl")
    iterator = fake.telegrams()
    await fake.connect()

    async with asyncio.timeout(1.0):
        wrapped = await iterator.__anext__()
    assert wrapped.rssi_dbm == -65
    assert wrapped.rorg is RORG.RORG_RPS

    await fake.aclose()


async def test_simulate_disconnect_reconnects() -> None:
    fake = FakeDongle()
    await fake.connect()

    iterator = fake.state_changes()
    await fake.simulate_disconnect()

    seen: list[StateChange] = []
    async with asyncio.timeout(1.0):
        async for change in iterator:
            seen.append(change)
            if change.new is State.CONNECTED:
                break
    states = [c.new for c in seen]
    assert State.RECONNECTING in states
    assert states[-1] is State.CONNECTED
    await fake.aclose()


async def test_simulate_connection_failure_retries() -> None:
    fake = FakeDongle()
    await fake.simulate_connection_failure(attempts=2)
    iterator = fake.state_changes()
    await fake.connect()
    seen: list[StateChange] = []
    async with asyncio.timeout(1.0):
        async for change in iterator:
            seen.append(change)
            if change.new is State.CONNECTED:
                break
    states = [c.new for c in seen]
    assert states.count(State.RECONNECTING) >= 2
    assert states[-1] is State.CONNECTED
    await fake.aclose()


async def test_overflow_burst(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_streams, "_OVERFLOW_WINDOW_S", 0.01)
    fake = FakeDongle(queue_size=4)
    warnings_iter = fake.warnings()
    await fake.connect()

    template = ERP1Telegram(
        rorg=RORG.RORG_RPS,
        telegram_data=bytes([0x10]),
        sender=EURID(0x01234567),
        status=0x30,
    )
    # Subscribe to telegrams *but* don't drain — forces overflow.
    fake.telegrams()
    for _ in range(20):
        await fake.push(template)
    await asyncio.sleep(0.05)

    async with asyncio.timeout(1.0):
        warning = await warnings_iter.__anext__()
    assert isinstance(warning, QueueOverflowWarning)
    assert warning.dropped_count > 0

    await fake.aclose()


async def test_aclose_idempotent() -> None:
    fake = FakeDongle()
    await fake.connect()
    await fake.aclose()
    assert fake.state is State.CLOSED
    await fake.aclose()  # should be a no-op
    assert fake.state is State.CLOSED


async def test_send_when_disconnected_raises() -> None:
    fake = FakeDongle()
    # never call connect()
    from enocean_async.protocol.esp3.packet import ESP3Packet, ESP3PacketType

    packet = ESP3Packet(packet_type=ESP3PacketType.RADIO_ERP1, data=b"\x00", optional=b"")
    with pytest.raises(ConnectionError):
        await fake.send(packet)


async def test_send_records_packet() -> None:
    from enocean_async.protocol.esp3.packet import ESP3Packet, ESP3PacketType

    fake = FakeDongle()
    await fake.connect()
    packet = ESP3Packet(packet_type=ESP3PacketType.RADIO_ERP1, data=b"\x00", optional=b"")
    result = await fake.send(packet)
    assert result.response is None
    assert fake.sent == [packet]
    await fake.aclose()


async def test_set_state_emits_state_change() -> None:
    fake = FakeDongle()
    iterator = fake.state_changes()
    fake.set_state(State.CONNECTED)
    async with asyncio.timeout(1.0):
        change = await iterator.__anext__()
    assert change.new is State.CONNECTED
    await fake.aclose()
