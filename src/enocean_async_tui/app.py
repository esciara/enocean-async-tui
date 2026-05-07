"""Phase-1 Textual app shell."""

from __future__ import annotations

import importlib.resources
import logging
from collections.abc import Callable
from pathlib import Path
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
from enocean_async_tui.dongle.autodiscovery import discover_dongles
from enocean_async_tui.settings import Settings
from enocean_async_tui.ui.messages import FilterChanged
from enocean_async_tui.ui.screens.sniffer import SnifferScreen
from enocean_async_tui.ui.workers.sniffer import SnifferWorker

_LOGGER = logging.getLogger("enocean_async_tui.app")

_TITLE = "EnOcean TUI"

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
    """Custom header showing title, dongle status, port, base-ID, and filter state."""

    status: reactive[State] = reactive(State.IDLE)
    fake_mode: reactive[bool] = reactive(False)
    demo_mode: reactive[bool] = reactive(False)
    scanning: reactive[bool] = reactive(False)
    port: reactive[str | None] = reactive(None)
    filter_id: reactive[int | None] = reactive(None)
    multi_dongle_ports: reactive[tuple[str, ...]] = reactive(())

    def render(self) -> str:
        if self.multi_dongle_ports:
            ports_str = ", ".join(self.multi_dongle_ports)
            return f"[b]{_TITLE}[/b] — [red]Multiple dongles found: {ports_str} — use --port to specify one[/red]"
        if self.scanning:
            return f"[b]{_TITLE}[/b] — [yellow]Scanning for dongles…[/yellow]"
        text = _STATUS_TEXT[self.status]
        style = _STATUS_STYLE[self.status]
        if self.demo_mode and self.status is State.CONNECTED:
            port_part = "[magenta]DEMO (fake dongle)[/magenta]"
        else:
            port_part = self.port or "–"
        filter_part = ""
        if self.filter_id is not None:
            filter_part = f"  [[b]FILTER: 0x{self.filter_id:08X}[/b]]"
        return (
            f"[b]{_TITLE}[/b] — [{style}]{text}[/{style}]"
            f"  {port_part}  Base-ID: –{filter_part}"
        )


class FallbackModal(ModalScreen[bool]):
    """`[Quit]` (default) / `[Continue with fake dongle]` modal."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        ("escape", "quit", "Quit"),
    ]

    def __init__(self, port: str | None) -> None:
        super().__init__()
        self._port = port

    def compose(self) -> ComposeResult:
        if self._port:
            message = f"Couldn't open serial port {self._port}.\nContinue in fake-dongle mode for testing?"
        else:
            message = "No EnOcean dongle found.\nContinue in fake-dongle mode for testing?"
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
        ("f", "toggle_filter", "Filter"),
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
        self._demo_mode: bool = False

    def compose(self) -> ComposeResult:
        yield StatusHeader(id="status-header")
        yield SnifferScreen()
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._launch_dongle(), name="dongle-launcher", group="dongle-launch")

    async def on_unmount(self) -> None:
        if self._dongle is not None:
            await self._dongle.aclose()
            self._dongle = None

    def action_toggle_filter(self) -> None:
        self.query_one(SnifferScreen).toggle_filter_input()

    def on_filter_changed(self, message: FilterChanged) -> None:
        self.query_one("#status-header", StatusHeader).filter_id = message.filter_id

    # ------------------------------------------------------------ internals

    async def _launch_dongle(self) -> None:
        if self._dongle_factory is not None:
            dongle = self._dongle_factory()
            self._fake_mode = isinstance(dongle, FakeDongle)
            self._demo_mode = False
            await self._connect_and_start(dongle, self._settings.port)
        elif self._settings.fake:
            fake = FakeDongle(realtime=True)
            await fake.connect()
            self._dongle = fake
            self._fake_mode = True
            self._demo_mode = True
            self._update_fake_suffix(port=None)
            self._start_workers(fake)
        elif self._settings.port is None:
            await self._run_autodiscovery()
        else:
            dongle = DongleService(self._settings.port)
            self._fake_mode = False
            self._demo_mode = False
            await self._connect_and_start(dongle, self._settings.port)

    async def _connect_and_start(self, dongle: Dongle, port: str | None) -> None:
        try:
            await dongle.connect()
        except ConnectionError:
            _LOGGER.warning("dongle: connect raised; offering fallback modal")
            await dongle.aclose()
            await self._handle_fallback(port)
            return
        self._dongle = dongle
        self._update_fake_suffix(port=port)
        self._start_workers(dongle)

    async def _run_autodiscovery(self) -> None:
        header = self.query_one("#status-header", StatusHeader)
        header.scanning = True
        try:
            ports = await discover_dongles()
        finally:
            header.scanning = False

        if not ports:
            await self._handle_fallback(None)
        elif len(ports) == 1:
            dongle = DongleService(ports[0])
            self._fake_mode = False
            await self._connect_and_start(dongle, ports[0])
        else:
            header.multi_dongle_ports = tuple(ports)

    async def _handle_fallback(self, port: str | None) -> None:
        accepted = await self.push_screen_wait(FallbackModal(port))
        if not accepted:
            self.exit(return_code=2)
            return
        _fixture = importlib.resources.files("enocean_async_tui.fixtures").joinpath("burst-300.jsonl")
        fake = FakeDongle(recording=Path(str(_fixture)), realtime=True)
        await fake.connect()
        self._dongle = fake
        self._fake_mode = True
        self._demo_mode = True
        self._update_fake_suffix(port=None)
        self._start_workers(fake)

    def _update_fake_suffix(self, *, port: str | None = None) -> None:
        header = self.query_one("#status-header", StatusHeader)
        header.fake_mode = self._fake_mode
        header.demo_mode = self._demo_mode
        header.port = port

    def on_filter_changed(self, message: FilterChanged) -> None:
        self.query_one("#status-header", StatusHeader).filter_id = message.filter_id

    def _start_workers(self, dongle: Dongle) -> None:
        header = self.query_one("#status-header", StatusHeader)
        header.status = dongle.state
        screen = self.query_one(SnifferScreen)
        sniffer = SnifferWorker(dongle, screen)
        screen.set_worker(sniffer)

        async def _state_worker() -> None:
            async for change in dongle.state_changes():
                header.status = change.new

        async def _warnings_worker() -> None:
            async for warning in dongle.warnings():
                self.notify(
                    f"Dropped {warning.dropped_count} telegrams since {warning.since.isoformat(timespec='seconds')}",
                    severity="warning",
                )

        self.run_worker(_state_worker(), name="state-worker", group="dongle-streams")
        self.run_worker(sniffer.run(), name="sniffer-worker", group="dongle-streams")
        self.run_worker(_warnings_worker(), name="warnings-worker", group="dongle-streams")
