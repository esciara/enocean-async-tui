from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Label


class EnOceanApp(App):  # type: ignore[type-arg]
    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("EnOcean TUI — connecting…")
        yield Footer()


def main() -> None:
    EnOceanApp().run()
