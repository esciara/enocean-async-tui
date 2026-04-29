"""In-memory `Dongle` implementation for tests and the runtime fallback."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from enocean_async.address import EURID
from enocean_async.gateway import SendResult
from enocean_async.protocol.erp1.rorg import RORG
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

_LOGGER = logging.getLogger("enocean_async_tui.dongle.fake")

DEFAULT_QUEUE_SIZE = 256

# Synthetic backoff for the in-memory reconnect loop. Mirrors the real
# service's `INITIAL_DELAY_S`. Module constant so tests can monkey-patch.
FAKE_RECONNECT_DELAY_S: float = 0.5


def _parse_erp1_frame(data: bytes) -> ERP1Telegram:
    """Parse a raw ERP1 frame: rorg(1) + telegram_data(N) + sender(4) + status(1)."""
    if len(data) < 7:
        raise ValueError(f"ERP1 frame too short: {len(data)} bytes")
    rorg = RORG(data[0])
    telegram_data = bytes(data[1:-5])
    sender_value = int.from_bytes(data[-5:-1], "big")
    status = data[-1]
    return ERP1Telegram(
        rorg=rorg,
        telegram_data=telegram_data,
        sender=EURID(sender_value),
        status=status,
    )


class FakeDongle:
    """In-memory `Dongle`. Same surface as `DongleService` plus test-only knobs."""

    sent: list[ESP3Packet]
    send_response: SendResult

    def __init__(
        self,
        *,
        recording: Path | None = None,
        realtime: bool = False,
        queue_size: int = DEFAULT_QUEUE_SIZE,
    ) -> None:
        self._recording = recording
        self._realtime = realtime
        self._queue_size = queue_size

        self._state: State = State.IDLE
        self._state_changes: _Broadcaster[StateChange] = _Broadcaster(queue_size=queue_size)
        self._warnings: _Broadcaster[QueueOverflowWarning] = _Broadcaster(queue_size=queue_size)
        self._telegrams: _TelegramBroadcaster = _TelegramBroadcaster(
            queue_size=queue_size,
            warnings=self._warnings,
        )

        self._replay_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._failures_remaining: int = 0
        self._closed = False

        self.sent = []
        self.send_response = SendResult(response=None, duration_ms=0.0)

    @property
    def state(self) -> State:
        return self._state

    async def connect(self) -> None:
        if self._closed:
            raise RuntimeError("FakeDongle is closed")
        self._set_state(State.CONNECTING)
        if self._failures_remaining > 0:
            self._failures_remaining -= 1
            self._set_state(State.RECONNECTING)
            # Simulate retry until success — the fake collapses backoff to zero
            # so tests stay fast.
            while self._failures_remaining > 0:
                self._failures_remaining -= 1
                self._set_state(State.CONNECTING)
                self._set_state(State.RECONNECTING)
            self._set_state(State.CONNECTING)
        self._set_state(State.CONNECTED)
        self._start_replay()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._replay_task is not None:
            self._replay_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._replay_task
            self._replay_task = None
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reconnect_task
            self._reconnect_task = None
        self._set_state(State.CLOSED)
        self._telegrams.close()
        self._state_changes.close()
        self._warnings.close()

    async def send(self, packet: ESP3Packet) -> SendResult:
        if self._state is not State.CONNECTED:
            raise ConnectionError(f"FakeDongle not connected (state={self._state.value})")
        self.sent.append(packet)
        return self.send_response

    def telegrams(self) -> AsyncIterator[RawTelegram]:
        return _iterate(self._telegrams.subscribe())

    def state_changes(self) -> AsyncIterator[StateChange]:
        return _iterate(self._state_changes.subscribe())

    def warnings(self) -> AsyncIterator[QueueOverflowWarning]:
        return _iterate(self._warnings.subscribe())

    # ------------------------------------------------------------------ test API

    async def push(
        self,
        telegram: ERP1Telegram,
        *,
        rssi_dbm: int | None = None,
    ) -> None:
        if rssi_dbm is not None:
            telegram = ERP1Telegram(
                rorg=telegram.rorg,
                telegram_data=telegram.telegram_data,
                sender=telegram.sender,
                status=telegram.status,
                sub_tel_num=telegram.sub_tel_num,
                rssi=rssi_dbm,
                sec_level=telegram.sec_level,
                destination=telegram.destination,
            )
        wrapped = RawTelegram(raw=telegram, received_at=datetime.now(tz=UTC))
        self._telegrams.publish(wrapped)

    async def push_raw(self, telegram: RawTelegram) -> None:
        self._telegrams.publish(telegram)

    async def simulate_disconnect(self) -> None:
        """Force CONNECTED → RECONNECTING. The fake then reconnects on its
        own (mirrors the real service); the reconnect happens asynchronously
        so subscribers can observe RECONNECTING before the next transition.
        """
        if self._state is not State.CONNECTED:
            return
        self._set_state(State.RECONNECTING)
        self._reconnect_task = asyncio.create_task(self._auto_reconnect())

    async def _auto_reconnect(self) -> None:
        try:
            await asyncio.sleep(FAKE_RECONNECT_DELAY_S)
            self._set_state(State.CONNECTING)
            await asyncio.sleep(0)
            self._set_state(State.CONNECTED)
            self._start_replay()
        except asyncio.CancelledError:  # pragma: no cover - cancellation path
            raise

    async def simulate_connection_failure(self, *, attempts: int = 1) -> None:
        self._failures_remaining = attempts

    def set_state(self, state: State) -> None:
        """Bypass the state machine for pathological-case tests."""
        self._set_state(state)

    # ------------------------------------------------------------------ internals

    def _set_state(self, new_state: State) -> None:
        old = self._state
        if old is new_state:
            return
        self._state = new_state
        self._state_changes.publish(
            StateChange(old=old, new=new_state, at=datetime.now(tz=UTC)),
        )

    def _start_replay(self) -> None:
        if self._recording is None:
            return
        if self._replay_task is not None and not self._replay_task.done():
            self._replay_task.cancel()
        self._replay_task = asyncio.create_task(self._replay_loop())

    async def _replay_loop(self) -> None:
        if self._recording is None:
            return
        try:
            previous_offset_ms = 0
            for line_no, line in enumerate(self._read_lines(self._recording), start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    _LOGGER.warning(
                        "fake-dongle: skipping invalid JSON at %s:%d (%s)",
                        self._recording,
                        line_no,
                        exc,
                    )
                    continue
                try:
                    telegram = _parse_erp1_frame(bytes.fromhex(record["telegram_hex"]))
                except (KeyError, ValueError) as exc:
                    _LOGGER.warning(
                        "fake-dongle: skipping unparseable record at %s:%d (%s)",
                        self._recording,
                        line_no,
                        exc,
                    )
                    continue

                rssi = record.get("rssi_dbm")
                if rssi is not None:
                    telegram = ERP1Telegram(
                        rorg=telegram.rorg,
                        telegram_data=telegram.telegram_data,
                        sender=telegram.sender,
                        status=telegram.status,
                        sub_tel_num=telegram.sub_tel_num,
                        rssi=int(rssi),
                        sec_level=telegram.sec_level,
                        destination=telegram.destination,
                    )

                if self._realtime:
                    offset_ms = int(record.get("t_offset_ms", 0))
                    delay_s = max(0, offset_ms - previous_offset_ms) / 1000.0
                    previous_offset_ms = offset_ms
                    if delay_s > 0:
                        await asyncio.sleep(delay_s)

                wrapped = RawTelegram(raw=telegram, received_at=datetime.now(tz=UTC))
                self._telegrams.publish(wrapped)
        except asyncio.CancelledError:  # pragma: no cover - cancellation path
            raise

    @staticmethod
    def _read_lines(path: Path) -> list[str]:
        return path.read_text(encoding="utf-8").splitlines()
