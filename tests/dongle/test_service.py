from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from enocean_async import Observable, Observation
from enocean_async.address import EURID
from enocean_async.gateway import SendResult
from enocean_async.protocol.erp1.rorg import RORG
from enocean_async.protocol.erp1.telegram import ERP1Telegram
from enocean_async.protocol.esp3.packet import ESP3Packet, ESP3PacketType

from enocean_async_tui.dongle import (
    DongleService,
    QueueOverflowWarning,
    State,
    _streams,
)
from enocean_async_tui.dongle import service as service_module


class FakeGateway:
    """Minimal `enocean_async.Gateway` test double."""

    instances: list[FakeGateway] = []

    def __init__(
        self,
        port: str,
        *,
        fail_times: int = 0,
        on_started: Callable[[FakeGateway], None] | None = None,
    ) -> None:
        self.port = port
        self._fail_times = fail_times
        self._erp1_callbacks: list[Callable[[ERP1Telegram], None]] = []
        self._observation_callbacks: list[Callable[[Observation], None]] = []
        self._started = False
        self._stopped = False
        self.send_calls: list[ESP3Packet] = []
        self.send_response = SendResult(response=None, duration_ms=1.0)
        self._on_started = on_started
        FakeGateway.instances.append(self)

    @property
    def is_connected(self) -> bool:
        return self._started and not self._stopped

    def add_erp1_received_callback(self, cb: Callable[[ERP1Telegram], None], sender_filter: Any = None) -> None:
        self._erp1_callbacks.append(cb)

    def add_observation_callback(self, cb: Callable[[Observation], None]) -> None:
        self._observation_callbacks.append(cb)

    async def start(self, auto_reconnect: bool = True) -> None:
        if self._fail_times > 0:
            self._fail_times -= 1
            raise ConnectionError(f"can't open {self.port}")
        self._started = True
        if self._on_started is not None:
            self._on_started(self)

    def stop(self) -> None:
        self._stopped = True

    async def send_esp3_packet(self, packet: ESP3Packet) -> SendResult:
        self.send_calls.append(packet)
        return self.send_response

    # Test helpers
    def emit_telegram(self, telegram: ERP1Telegram) -> None:
        for cb in self._erp1_callbacks:
            cb(telegram)

    def emit_disconnected_observation(self) -> None:
        observation = Observation(
            device=EURID(0),
            entity="connection_status",
            values={Observable.CONNECTION_STATUS: "disconnected"},
            timestamp=datetime.now(tz=UTC).timestamp(),
        )
        for cb in self._observation_callbacks:
            cb(observation)


@pytest.fixture(autouse=True)
def _instant_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "INITIAL_DELAY_S", 0.0)
    monkeypatch.setattr(service_module, "MAX_DELAY_S", 0.0)
    monkeypatch.setattr(service_module, "JITTER", 0.0)


@pytest.fixture
def reset_fake_gateway_instances() -> None:
    FakeGateway.instances.clear()


def _factory(*, fail_times: int = 0) -> Callable[[str], FakeGateway]:
    counter = {"remaining": fail_times}

    def make(port: str) -> FakeGateway:
        ft = counter["remaining"]
        counter["remaining"] = 0  # only the first instance fails
        return FakeGateway(port, fail_times=ft)

    return make


async def test_connect_happy_path(reset_fake_gateway_instances: None) -> None:
    service = DongleService("/dev/null", gateway_factory=_factory())
    iterator = service.state_changes()
    await service.connect()
    assert service.state is State.CONNECTED
    seen = []
    async with asyncio.timeout(1.0):
        async for change in iterator:
            seen.append(change)
            if len(seen) == 2:
                break
    assert seen[0].old is State.IDLE
    assert seen[0].new is State.CONNECTING
    assert seen[1].new is State.CONNECTED
    await service.aclose()


async def test_connect_failure_then_success(reset_fake_gateway_instances: None) -> None:
    service = DongleService("/dev/null", gateway_factory=_factory(fail_times=1))
    iterator = service.state_changes()
    await service.connect()
    seen = []
    async with asyncio.timeout(1.0):
        async for change in iterator:
            seen.append(change)
            if change.new is State.CONNECTED:
                break
    states = [c.new for c in seen]
    assert State.RECONNECTING in states
    assert states[-1] is State.CONNECTED
    await service.aclose()


async def test_telegram_callback_delivers_raw_telegram(reset_fake_gateway_instances: None) -> None:
    service = DongleService("/dev/null", gateway_factory=_factory())
    telegrams_iter = service.telegrams()
    await service.connect()

    gateway = FakeGateway.instances[-1]
    telegram = ERP1Telegram(
        rorg=RORG.RORG_RPS,
        telegram_data=bytes([0x10]),
        sender=EURID(0x01234567),
        status=0x30,
        rssi=180,
    )
    gateway.emit_telegram(telegram)

    async with asyncio.timeout(1.0):
        wrapped = await telegrams_iter.__anext__()
    assert wrapped.rssi_dbm == 180
    assert wrapped.rorg is RORG.RORG_RPS
    assert wrapped.received_at.tzinfo is UTC
    await service.aclose()


async def test_queue_overflow_emits_one_warning(
    reset_fake_gateway_instances: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_streams, "_OVERFLOW_WINDOW_S", 0.05)
    service = DongleService(
        "/dev/null",
        queue_size=256,
        gateway_factory=_factory(),
    )
    # subscribe a telegram iterator (256 capacity), but never drain
    service.telegrams()
    warnings_iter = service.warnings()
    await service.connect()

    gateway = FakeGateway.instances[-1]
    telegram = ERP1Telegram(
        rorg=RORG.RORG_RPS,
        telegram_data=bytes([0x10]),
        sender=EURID(0x01234567),
        status=0x30,
    )
    for _ in range(300):
        gateway.emit_telegram(telegram)

    await asyncio.sleep(0.1)

    warnings_seen: list[QueueOverflowWarning] = []
    try:
        async with asyncio.timeout(0.2):
            async for warning in warnings_iter:
                warnings_seen.append(warning)
    except TimeoutError:
        pass

    assert len(warnings_seen) == 1
    assert warnings_seen[0].dropped_count == 44
    await service.aclose()


async def test_send_when_disconnected_raises(reset_fake_gateway_instances: None) -> None:
    service = DongleService("/dev/null", gateway_factory=_factory())
    packet = ESP3Packet(packet_type=ESP3PacketType.RADIO_ERP1, data=b"\x00", optional=b"")
    with pytest.raises(ConnectionError):
        await service.send(packet)


async def test_send_when_connected_forwards_to_gateway(reset_fake_gateway_instances: None) -> None:
    service = DongleService("/dev/null", gateway_factory=_factory())
    await service.connect()
    gateway = FakeGateway.instances[-1]
    packet = ESP3Packet(packet_type=ESP3PacketType.RADIO_ERP1, data=b"\x00", optional=b"")
    result = await service.send(packet)
    assert gateway.send_calls == [packet]
    assert result is gateway.send_response
    await service.aclose()


async def test_aclose_terminates_iterators(reset_fake_gateway_instances: None) -> None:
    service = DongleService("/dev/null", gateway_factory=_factory())
    state_iter = service.state_changes()
    telegrams_iter = service.telegrams()
    warnings_iter = service.warnings()
    await service.connect()
    await service.aclose()
    assert service.state is State.CLOSED

    # All three iterators terminate.
    async def collect(it: Any) -> list[Any]:
        out = []
        async with asyncio.timeout(1.0):
            async for x in it:
                out.append(x)
        return out

    await collect(state_iter)
    await collect(telegrams_iter)
    await collect(warnings_iter)


async def test_aclose_idempotent(reset_fake_gateway_instances: None) -> None:
    service = DongleService("/dev/null", gateway_factory=_factory())
    await service.connect()
    await service.aclose()
    await service.aclose()


async def test_connect_after_close_raises(reset_fake_gateway_instances: None) -> None:
    service = DongleService("/dev/null", gateway_factory=_factory())
    await service.aclose()
    with pytest.raises(RuntimeError):
        await service.connect()


async def test_disconnected_observation_triggers_reconnect(
    reset_fake_gateway_instances: None,
) -> None:
    service = DongleService("/dev/null", gateway_factory=_factory())
    iterator = service.state_changes()
    await service.connect()
    gateway = FakeGateway.instances[-1]
    gateway.emit_disconnected_observation()

    seen = []
    async with asyncio.timeout(1.0):
        async for change in iterator:
            seen.append(change)
            if change.new is State.CONNECTED and any(c.new is State.RECONNECTING for c in seen):
                break
    states = [c.new for c in seen]
    assert State.RECONNECTING in states
    assert states[-1] is State.CONNECTED
    await service.aclose()


async def test_async_context_manager(reset_fake_gateway_instances: None) -> None:
    async with DongleService("/dev/null", gateway_factory=_factory()) as service:
        assert service.state is State.CONNECTED
    assert service.state is State.CLOSED
