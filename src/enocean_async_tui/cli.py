"""Console-script entry point.

Loads Settings, configures logging once, and runs the Textual app.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence

from enocean_async_tui.app import EnoceanTuiApp
from enocean_async_tui.settings import Settings


def main(argv: Sequence[str] | None = None) -> int:
    settings = Settings.from_args(argv)
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    app = EnoceanTuiApp(settings)
    app.run()
    return 0
