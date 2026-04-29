"""Phase-0 Textual app shell."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Label, Static

from enocean_async_tui.dongle import (
    Dongle,
    DongleService,
    FakeDongle,
    State,
)
from enocean_async_tui.settings import Settings

_LOGGER = logging.getLogger("enocean_async_tui.app")

_TITLE = "EnOcean TUI"
_FAKE_SUFFIX = " (fake-dongle mode)"

_STATUS_TEXT: dict[State, str] = {
    State.IDLE: "connecting…",
    State.CONNECTING: "connecting…",
    State.CONNECTED: "connected",
    State.RECONNECTING: "reconnecting…",
    State.CLOSED: "closed",
}

_STATUS_STYLE: dict[State, str] = {
    State.IDLE: "dim",
    State.CONNECTING: "yellow",
    State.CONNECTED: "green",
    State.RECONNECTING: "yellow",
    State.CLOSED: "red",
}


class StatusHeader(Static):
    """Custom header showing the title and dongle status."""

    status: reactive[State] = reactive(State.IDLE)
    fake_mode: reactive[bool] = reactive(False)

    def render(self) -> str:
        text = _STATUS_TEXT[self.status]
        style = _STATUS_STYLE[self.status]
        if self.fake_mode and self.status is State.CONNECTED:
            text = f"{text}{_FAKE_SUFFIX}"
            style = "magenta"
        return f"[b]{_TITLE}[/b] — [{style}]{text}[/{style}]"


class FallbackModal(ModalScreen[bool]):
    """`[Quit]` (default) / `[Continue with fake dongle]` modal."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        ("escape", "quit", "Quit"),
    ]

    def __init__(self, port: str) -> None:
        super().__init__()
        self._port = port

    def compose(self) -> ComposeResult:
        message = f"Couldn't open serial port {self._port}.\nContinue in fake-dongle mode for testing?"
        yield Vertical(
            Label("Dongle not available", id="modal-title"),
            Label(message, id="modal-body"),
            Center(
                Button("Quit", id="modal-quit", variant="primary"),
                Button("Continue with fake dongle", id="modal-fake"),
            ),
            id="fallback-modal",
        )

    def on_mount(self) -> None:
        self.query_one("#modal-quit", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "modal-quit":
            self.dismiss(False)
        elif event.button.id == "modal-fake":
            self.dismiss(True)

    def action_quit(self) -> None:
        self.dismiss(False)


class EnoceanTuiApp(App[int]):
    """Phase-0 app shell. Owns the dongle lifecycle."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        settings: Settings,
        *,
        dongle_factory: Callable[[], Dongle] | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._dongle_factory = dongle_factory
        self._dongle: Dongle | None = None
        self._fake_mode: bool = False

    def compose(self) -> ComposeResult:
        yield StatusHeader(id="status-header")
        yield Label("Phase 0 — placeholder", id="main-pane")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._launch_dongle(), name="dongle-launcher", group="dongle-launch")

    async def on_unmount(self) -> None:
        if self._dongle is not None:
            await self._dongle.aclose()
            self._dongle = None

    # ------------------------------------------------------------ internals

    async def _launch_dongle(self) -> None:
        if self._dongle_factory is not None:
            dongle = self._dongle_factory()
            self._fake_mode = isinstance(dongle, FakeDongle)
        else:
            dongle = DongleService(self._settings.port)
            self._fake_mode = False

        try:
            await dongle.connect()
        except ConnectionError:
            _LOGGER.warning("dongle: connect raised; offering fallback modal")
            await dongle.aclose()
            await self._handle_fallback()
            return

        self._dongle = dongle
        self._update_fake_suffix()
        self._start_workers(dongle)

    async def _handle_fallback(self) -> None:
        accepted = await self.push_screen_wait(FallbackModal(self._settings.port))
        if not accepted:
            self.exit(return_code=2)
            return
        fake = FakeDongle(realtime=True)
        await fake.connect()
        self._dongle = fake
        self._fake_mode = True
        self._update_fake_suffix()
        self._start_workers(fake)

    def _update_fake_suffix(self) -> None:
        header = self.query_one("#status-header", StatusHeader)
        header.fake_mode = self._fake_mode

    def _start_workers(self, dongle: Dongle) -> None:
        header = self.query_one("#status-header", StatusHeader)
        header.status = dongle.state

        async def _state_worker() -> None:
            async for change in dongle.state_changes():
                header.status = change.new

        async def _telegrams_worker() -> None:
            async for _telegram in dongle.telegrams():
                # Phase 1+ will log this to a list view.
                pass

        async def _warnings_worker() -> None:
            async for warning in dongle.warnings():
                self.notify(
                    f"Dropped {warning.dropped_count} telegrams since {warning.since.isoformat(timespec='seconds')}",
                    severity="warning",
                )

        self.run_worker(_state_worker(), name="state-worker", group="dongle-streams")
        self.run_worker(_telegrams_worker(), name="telegrams-worker", group="dongle-streams")
        self.run_worker(_warnings_worker(), name="warnings-worker", group="dongle-streams")
