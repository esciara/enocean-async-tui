"""`DongleService` — Phase-0 wrapper around `enocean_async.Gateway`."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import TYPE_CHECKING

from enocean_async import Gateway, Observable, Observation
from enocean_async.gateway import SendResult
from enocean_async.protocol.erp1.telegram import ERP1Telegram
from enocean_async.protocol.esp3.packet import ESP3Packet

from enocean_async_tui.dongle._streams import (
    _Broadcaster,
    _iterate,
    _TelegramBroadcaster,
)
from enocean_async_tui.dongle.protocol import (
    QueueOverflowWarning,
    State,
    StateChange,
)
from enocean_async_tui.dongle.types import RawTelegram

if TYPE_CHECKING:  # pragma: no cover
    from typing import Self

_LOGGER = logging.getLogger("enocean_async_tui.dongle")

# Backoff parameters (locked by Phase-0 spec). Module-level so tests can monkey-patch.
INITIAL_DELAY_S: float = 0.5
MAX_DELAY_S: float = 30.0
MULTIPLIER: float = 2.0
JITTER: float = 0.1  # ±10 %

TELEGRAM_QUEUE_SIZE: int = 256

GatewayFactory = Callable[[str], Gateway]


def _default_gateway_factory(port: str) -> Gateway:
    return Gateway(port=port)


class DongleService:
    """Owns the serial connection and exposes telegrams + state changes + warnings."""

    def __init__(
        self,
        port: str,
        *,
        queue_size: int | None = None,
        gateway_factory: GatewayFactory | None = None,
    ) -> None:
        self._port = port
        self._queue_size = queue_size if queue_size is not None else TELEGRAM_QUEUE_SIZE
        self._gateway_factory: GatewayFactory = gateway_factory or _default_gateway_factory

        self._state: State = State.IDLE
        self._gateway: Gateway | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._reconnect_attempt: int = 0
        self._closed = False

        self._state_changes: _Broadcaster[StateChange] = _Broadcaster(queue_size=self._queue_size)
        self._warnings: _Broadcaster[QueueOverflowWarning] = _Broadcaster(queue_size=self._queue_size)
        self._telegrams: _TelegramBroadcaster = _TelegramBroadcaster(
            queue_size=self._queue_size,
            warnings=self._warnings,
        )

    # ----------------------------------------------------------- public surface

    @property
    def state(self) -> State:
        return self._state

    async def connect(self) -> None:
        if self._closed:
            raise RuntimeError("DongleService is closed")
        if self._state in (State.CONNECTING, State.CONNECTED, State.RECONNECTING):
            return
        await self._attempt_connect()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reconnect_task
            self._reconnect_task = None
        if self._gateway is not None:
            try:
                self._gateway.stop()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("dongle: error stopping gateway")
            self._gateway = None
        self._set_state(State.CLOSED)
        self._telegrams.close()
        self._state_changes.close()
        self._warnings.close()

    async def send(self, packet: ESP3Packet) -> SendResult:
        if self._state is not State.CONNECTED or self._gateway is None:
            raise ConnectionError(
                f"DongleService not connected (state={self._state.value})",
            )
        return await self._gateway.send_esp3_packet(packet)

    def telegrams(self) -> AsyncIterator[RawTelegram]:
        return _iterate(self._telegrams.subscribe())

    def state_changes(self) -> AsyncIterator[StateChange]:
        return _iterate(self._state_changes.subscribe())

    def warnings(self) -> AsyncIterator[QueueOverflowWarning]:
        return _iterate(self._warnings.subscribe())

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    # ----------------------------------------------------------- internals

    async def _attempt_connect(self) -> None:
        self._set_state(State.CONNECTING)
        gateway = self._gateway_factory(self._port)
        gateway.add_erp1_received_callback(self._on_erp1)
        gateway.add_observation_callback(self._on_observation)
        try:
            await gateway.start(auto_reconnect=False)
        except (ConnectionError, OSError) as exc:
            _LOGGER.warning("dongle: connect failed: %s", exc)
            with contextlib.suppress(Exception):
                gateway.stop()
            self._gateway = None
            self._schedule_reconnect()
            return
        self._gateway = gateway
        self._reconnect_attempt = 0
        self._set_state(State.CONNECTED)

    def _schedule_reconnect(self) -> None:
        if self._closed:
            return
        self._set_state(State.RECONNECTING)
        delay = self._compute_backoff(self._reconnect_attempt)
        self._reconnect_attempt += 1
        loop = asyncio.get_running_loop()
        self._reconnect_task = loop.create_task(self._reconnect_after(delay))

    async def _reconnect_after(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        if self._closed:
            return
        await self._attempt_connect()

    @staticmethod
    def _compute_backoff(attempt: int) -> float:
        base = min(INITIAL_DELAY_S * (MULTIPLIER**attempt), MAX_DELAY_S)
        return base * random.uniform(1.0 - JITTER, 1.0 + JITTER)

    def _on_erp1(self, telegram: ERP1Telegram) -> None:
        wrapped = RawTelegram(raw=telegram, received_at=datetime.now(tz=UTC))
        self._telegrams.publish(wrapped)
        _LOGGER.debug(
            "dongle: telegram sender=%s rorg=%s",
            telegram.sender,
            telegram.rorg.name,
        )

    def _on_observation(self, observation: Observation) -> None:
        if observation.entity != "connection_status":
            return
        status = observation.values.get(Observable.CONNECTION_STATUS)
        _LOGGER.info("dongle: upstream connection_status=%s", status)
        if status == "disconnected" and self._state is State.CONNECTED:
            self._handle_lost_connection()

    def _handle_lost_connection(self) -> None:
        if self._gateway is not None:
            try:
                self._gateway.stop()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("dongle: error stopping gateway after loss")
            self._gateway = None
        self._schedule_reconnect()

    def _set_state(self, new_state: State) -> None:
        old = self._state
        if old is new_state:
            return
        self._state = new_state
        _LOGGER.info("dongle: %s -> %s", old.value, new_state.value)
        self._state_changes.publish(
            StateChange(old=old, new=new_state, at=datetime.now(tz=UTC)),
        )
