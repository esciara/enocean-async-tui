"""Internal helpers shared by `DongleService` and `FakeDongle`.

A `_Broadcaster[T]` hands out fresh bounded-queue async iterators to each
subscriber. Late joiners do not see prior events.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Generic, TypeVar

from enocean_async_tui.dongle.protocol import QueueOverflowWarning
from enocean_async_tui.dongle.types import RawTelegram

T = TypeVar("T")

# Window during which overflow drops are accumulated before emitting a single
# warning. Module-level so tests can monkey-patch it.
_OVERFLOW_WINDOW_S: float = 1.0


class _SubscriberClosed:
    """Sentinel pushed into a queue to terminate its async iterator."""


_CLOSE_SENTINEL: _SubscriberClosed = _SubscriberClosed()


class _Broadcaster(Generic[T]):  # noqa: UP046
    """Multiplexes events across N independent bounded queues."""

    def __init__(self, *, queue_size: int) -> None:
        self._queue_size = queue_size
        self._subscribers: list[asyncio.Queue[T | _SubscriberClosed]] = []
        self._closed = False

    def subscribe(self) -> asyncio.Queue[T | _SubscriberClosed]:
        queue: asyncio.Queue[T | _SubscriberClosed] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.append(queue)
        if self._closed:
            queue.put_nowait(_CLOSE_SENTINEL)
        return queue

    def publish(self, event: T) -> None:
        if self._closed:
            return
        for queue in self._subscribers:
            self._enqueue(queue, event)

    def _enqueue(self, queue: asyncio.Queue[T | _SubscriberClosed], event: T) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
            queue.put_nowait(event)
            self._on_overflow(queue)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for queue in self._subscribers:
            self._enqueue_sentinel(queue)

    def _enqueue_sentinel(self, queue: asyncio.Queue[T | _SubscriberClosed]) -> None:
        try:
            queue.put_nowait(_CLOSE_SENTINEL)
        except asyncio.QueueFull:
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
            queue.put_nowait(_CLOSE_SENTINEL)

    def _on_overflow(self, queue: asyncio.Queue[T | _SubscriberClosed]) -> None:
        """Subclass hook; no-op by default."""


@dataclass(slots=True)
class _OverflowAccumulator:
    since: datetime
    count: int


class _TelegramBroadcaster(_Broadcaster[RawTelegram]):
    """Broadcasts telegrams. Per-subscriber overflows are accumulated in a
    sliding window and forwarded to the warnings broadcaster as a single
    `QueueOverflowWarning(dropped_count, since)` event when the window closes.
    """

    def __init__(self, *, queue_size: int, warnings: _Broadcaster[QueueOverflowWarning]) -> None:
        super().__init__(queue_size=queue_size)
        self._warnings = warnings
        self._overflow_state: dict[int, _OverflowAccumulator] = {}

    def _on_overflow(self, queue: asyncio.Queue[RawTelegram | _SubscriberClosed]) -> None:
        key = id(queue)
        state = self._overflow_state.get(key)
        if state is None:
            state = _OverflowAccumulator(since=datetime.now(tz=UTC), count=0)
            self._overflow_state[key] = state
            loop = asyncio.get_running_loop()
            loop.call_later(_OVERFLOW_WINDOW_S, self._flush, queue)
        state.count += 1

    def _flush(self, queue: asyncio.Queue[RawTelegram | _SubscriberClosed]) -> None:
        state = self._overflow_state.pop(id(queue), None)
        if state is None or state.count <= 0:
            return
        self._warnings.publish(
            QueueOverflowWarning(dropped_count=state.count, since=state.since),
        )

    def close(self) -> None:
        for queue in list(self._subscribers):
            self._flush(queue)
        super().close()


async def _iterate(queue: asyncio.Queue[T | _SubscriberClosed]) -> AsyncIterator[T]:  # noqa: UP047
    while True:
        item = await queue.get()
        if isinstance(item, _SubscriberClosed):
            return
        yield item
