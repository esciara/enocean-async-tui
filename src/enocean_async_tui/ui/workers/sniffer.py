"""SnifferWorker — Phase 1-A task 3 (eat-x32)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from enocean_async.protocol.erp1.errors import ERP1ParseError
from textual.message_pump import MessagePump

from enocean_async_tui.dongle.protocol import Dongle, State, StateChange
from enocean_async_tui.dongle.types import RawTelegram
from enocean_async_tui.ui.messages import ParseWarning, TelegramReceived

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger("enocean_async_tui.ui.workers.sniffer")

PAUSE_BUFFER_SIZE = 256


class DongleDisconnected(Exception):
    """Raised internally when the dongle enters RECONNECTING state."""


class SnifferWorker:
    """Iterates ``DongleService.telegrams()`` and posts :class:`TelegramReceived` messages.

    Pause / resume
    --------------
    While paused, incoming telegrams accumulate in a bounded deque (maxlen 256).
    Overflow silently drops the oldest entry and increments ``_dropped_count``.
    On resume the buffer is flushed in order.

    Reconnect
    ---------
    The outer loop catches :exc:`DongleDisconnected` (raised by the inner
    iterator when the dongle enters *RECONNECTING* state) and awaits the next
    *CONNECTED* state-change event before re-subscribing to telegrams.

    Cancellation
    ------------
    ``CancelledError`` is never caught — it propagates so Textual Worker
    shutdown completes cleanly.
    """

    def __init__(self, service: Dongle, app: MessagePump) -> None:
        self._service = service
        self._app = app
        self._paused = False
        self._pause_buffer: deque[RawTelegram] = deque(maxlen=PAUSE_BUFFER_SIZE)
        self._dropped_count = 0

    # ---------------------------------------------------------------------- public

    async def run(self) -> None:
        while True:
            try:
                async for telegram in self._iter_until_disconnect():
                    try:
                        if self._paused:
                            if len(self._pause_buffer) == self._pause_buffer.maxlen:
                                self._dropped_count += 1
                            self._pause_buffer.append(telegram)
                        else:
                            self._app.post_message(TelegramReceived(telegram))
                    except asyncio.CancelledError:
                        raise
                    except ERP1ParseError as exc:
                        _LOGGER.warning("sniffer: parse error: %s", exc)
                        self._app.post_message(ParseWarning(exc))
            except DongleDisconnected:
                pass
            await self._wait_for_reconnect()

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False
        while self._pause_buffer:
            telegram = self._pause_buffer.popleft()
            self._app.post_message(TelegramReceived(telegram))
        self._dropped_count = 0

    def clear_buffer(self) -> None:
        self._pause_buffer.clear()
        self._dropped_count = 0

    # ---------------------------------------------------------------------- internals

    async def _iter_until_disconnect(
        self,
    ) -> AsyncGenerator[RawTelegram]:
        """Yield telegrams until the dongle enters RECONNECTING, then raise DongleDisconnected."""
        tel_iter = self._service.telegrams()
        sc_iter = self._service.state_changes()

        tel_task: asyncio.Task[RawTelegram] = asyncio.create_task(
            tel_iter.__anext__()  # type: ignore[arg-type]
        )
        sc_task: asyncio.Task[StateChange] = asyncio.create_task(
            sc_iter.__anext__()  # type: ignore[arg-type]
        )

        try:
            while True:
                done, _ = await asyncio.wait(
                    {tel_task, sc_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # State change takes priority over telegram delivery.
                if sc_task in done:
                    try:
                        change = sc_task.result()
                    except StopAsyncIteration:
                        tel_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError, Exception):
                            await tel_task
                        return
                    if change.new is State.RECONNECTING:
                        tel_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError, Exception):
                            await tel_task
                        raise DongleDisconnected
                    sc_task = asyncio.create_task(
                        sc_iter.__anext__()  # type: ignore[arg-type]
                    )

                if tel_task in done:
                    try:
                        telegram = tel_task.result()
                    except StopAsyncIteration:
                        sc_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError, Exception):
                            await sc_task
                        return
                    tel_task = asyncio.create_task(
                        tel_iter.__anext__()  # type: ignore[arg-type]
                    )
                    yield telegram
        finally:
            # Cancel any still-pending tasks first.
            for _task in (tel_task, sc_task):
                if not _task.done():
                    _task.cancel()
            # Always retrieve results/exceptions so asyncio does not log
            # "Task exception was never retrieved" warnings.
            for _task in (tel_task, sc_task):
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await _task

    async def _wait_for_reconnect(self) -> None:
        """Block until the dongle reports CONNECTED; does not busy-poll."""
        async for change in self._service.state_changes():
            if change.new is State.CONNECTED:
                return
