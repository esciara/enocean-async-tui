"""Tests for SnifferWorker (eat-x32)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from enocean_async.address import EURID
from enocean_async.protocol.erp1.errors import ERP1ParseError
from enocean_async.protocol.erp1.rorg import RORG
from enocean_async.protocol.erp1.telegram import ERP1Telegram

from enocean_async_tui.dongle.fake import FakeDongle
from enocean_async_tui.ui.messages import ParseWarning, TelegramReceived
from enocean_async_tui.ui.workers.sniffer import SnifferWorker


def _make_telegram(sender: int = 0x01234567) -> ERP1Telegram:
    return ERP1Telegram(
        rorg=RORG.RORG_RPS,
        telegram_data=bytes([0x10]),
        sender=EURID(sender),
        status=0x30,
    )


class _FakeApp:
    """Minimal app stub that records posted messages."""

    def __init__(self, *, on_post: Callable[[Any], None] | None = None) -> None:
        self.messages: list[Any] = []
        self._on_post = on_post

    def post_message(self, message: Any) -> bool:
        if self._on_post is not None:
            self._on_post(message)
        self.messages.append(message)
        return True


async def test_pause_buffer_overflow() -> None:
    """257th entry drops the oldest; _dropped_count increments."""
    # Use a larger queue_size so the broadcaster does not drop items before the
    # pause buffer sees them (broadcaster maxsize == 256 by default, which would
    # drop the very first telegram before the worker gets it).
    fake = FakeDongle(queue_size=1000)
    await fake.connect()
    app = _FakeApp()
    worker = SnifferWorker(fake, app)  # type: ignore[arg-type]
    worker.pause()

    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0)  # let run() start

    for i in range(257):
        await fake.push(_make_telegram(sender=i))

    # Give worker time to process all telegrams
    async with asyncio.timeout(2.0):
        while len(worker._pause_buffer) < 256:  # noqa: SLF001
            await asyncio.sleep(0.01)
        # Also wait for dropped_count to be updated
        while worker._dropped_count < 1:  # noqa: SLF001
            await asyncio.sleep(0.01)

    assert len(worker._pause_buffer) == 256  # noqa: SLF001
    assert worker._dropped_count == 1  # noqa: SLF001
    # The oldest (sender=0) is dropped; sender=1 is now oldest
    first_in_buffer = next(iter(worker._pause_buffer))  # noqa: SLF001
    assert int(first_in_buffer.sender) == 1  # noqa: SLF001

    task.cancel()
    with pytest.raises((asyncio.CancelledError, Exception)):
        await task
    await fake.aclose()


async def test_clear_while_paused() -> None:
    """clear_buffer() empties both the pause buffer and the dropped counter."""
    fake = FakeDongle()
    await fake.connect()
    app = _FakeApp()
    worker = SnifferWorker(fake, app)  # type: ignore[arg-type]
    worker.pause()

    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0)

    for i in range(10):
        await fake.push(_make_telegram(sender=i))

    async with asyncio.timeout(1.0):
        while len(worker._pause_buffer) < 10:  # noqa: SLF001
            await asyncio.sleep(0.01)

    worker.clear_buffer()

    assert len(worker._pause_buffer) == 0  # noqa: SLF001
    assert worker._dropped_count == 0  # noqa: SLF001
    assert len([m for m in app.messages if isinstance(m, TelegramReceived)]) == 0

    task.cancel()
    with pytest.raises((asyncio.CancelledError, Exception)):
        await task
    await fake.aclose()


async def test_reconnect_resumes_streaming() -> None:
    """Worker re-enters loop after disconnect + reconnect; no busy-polling."""
    fake = FakeDongle()
    await fake.connect()
    app = _FakeApp()
    worker = SnifferWorker(fake, app)  # type: ignore[arg-type]

    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0)

    # Push telegram before disconnect
    await fake.push(_make_telegram(sender=0xAAAA0001))
    async with asyncio.timeout(1.0):
        while not any(isinstance(m, TelegramReceived) and int(m.telegram.sender) == 0xAAAA0001 for m in app.messages):
            await asyncio.sleep(0.01)

    pre_disconnect_count = len(app.messages)

    # Simulate disconnect; FakeDongle auto-reconnects after FAKE_RECONNECT_DELAY_S
    await fake.simulate_disconnect()

    # Wait for reconnect to complete
    from enocean_async_tui.dongle.fake import FAKE_RECONNECT_DELAY_S
    from enocean_async_tui.dongle.protocol import State

    async with asyncio.timeout(FAKE_RECONNECT_DELAY_S * 5 + 1.0):
        while fake.state is not State.CONNECTED:
            await asyncio.sleep(0.01)

    # Give worker a moment to re-enter the streaming loop
    await asyncio.sleep(0.05)

    # Push telegram after reconnect
    await fake.push(_make_telegram(sender=0xBBBB0002))
    async with asyncio.timeout(1.0):
        while not any(isinstance(m, TelegramReceived) and int(m.telegram.sender) == 0xBBBB0002 for m in app.messages):
            await asyncio.sleep(0.01)

    post_reconnect_msgs = [
        m
        for m in app.messages[pre_disconnect_count:]
        if isinstance(m, TelegramReceived) and int(m.telegram.sender) == 0xBBBB0002
    ]
    assert len(post_reconnect_msgs) >= 1

    task.cancel()
    with pytest.raises((asyncio.CancelledError, Exception)):
        await task
    await fake.aclose()


async def test_parse_error_continues() -> None:
    """Worker posts ParseWarning on ERP1ParseError in inner body; iteration continues."""
    fake = FakeDongle()
    await fake.connect()

    bad_sender = 0xDEAD0001
    good_sender = 0xBEEF0002
    call_count = 0

    posted: list[Any] = []

    def post_message(msg: Any) -> bool:
        nonlocal call_count
        posted.append(msg)
        call_count += 1
        if isinstance(msg, TelegramReceived) and int(msg.telegram.sender) == bad_sender:
            raise ERP1ParseError("malformed telegram")
        return True

    app = MagicMock()
    app.post_message.side_effect = post_message

    worker = SnifferWorker(fake, app)  # type: ignore[arg-type]
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0)

    # Inject the "bad" telegram — will trigger ERP1ParseError in inner body
    await fake.push(_make_telegram(sender=bad_sender))

    # Wait for ParseWarning to appear
    async with asyncio.timeout(1.0):
        while not any(isinstance(m, ParseWarning) for m in posted):
            await asyncio.sleep(0.01)

    # Inject a good telegram — worker should continue after parse error
    await fake.push(_make_telegram(sender=good_sender))

    async with asyncio.timeout(1.0):
        while not any(isinstance(m, TelegramReceived) and int(m.telegram.sender) == good_sender for m in posted):
            await asyncio.sleep(0.01)

    assert any(isinstance(m, ParseWarning) for m in posted)
    assert any(isinstance(m, TelegramReceived) and int(m.telegram.sender) == good_sender for m in posted)

    task.cancel()
    with pytest.raises((asyncio.CancelledError, Exception)):
        await task
    await fake.aclose()


async def test_cancelled_error_propagates() -> None:
    """CancelledError is NOT swallowed — it propagates out of run()."""
    fake = FakeDongle()
    await fake.connect()
    app = _FakeApp()
    worker = SnifferWorker(fake, app)  # type: ignore[arg-type]

    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0)  # let task start

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    await fake.aclose()
