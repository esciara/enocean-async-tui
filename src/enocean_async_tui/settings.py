"""Phase-0 configuration loader.

CLI flags > env vars > defaults. Pure: no I/O beyond reading the env mapping.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

_LOG_LEVELS: tuple[LogLevel, ...] = ("DEBUG", "INFO", "WARNING", "ERROR")

DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_LOG_LEVEL: LogLevel = "INFO"

ENV_PREFIX = "ENOCEAN_TUI_"


class SettingsError(ValueError):
    """Raised by Settings.from_args on invalid env-var values."""


@dataclass(frozen=True, slots=True)
class Settings:
    port: str
    log_level: LogLevel

    @classmethod
    def from_args(
        cls,
        argv: Sequence[str] | None = None,
        *,
        env: Mapping[str, str] | None = None,
    ) -> Settings:
        """Parse argv (defaults to sys.argv[1:]) and env (defaults to os.environ).

        Pure and deterministic: side effects are limited to argparse's
        SystemExit on bad CLI input.
        """
        environ: Mapping[str, str] = env if env is not None else os.environ

        parser = argparse.ArgumentParser(prog="enocean-tui")
        parser.add_argument("--port", default=None)
        parser.add_argument(
            "--log-level",
            choices=_LOG_LEVELS,
            default=None,
        )
        ns = parser.parse_args(argv)

        port = ns.port or environ.get(f"{ENV_PREFIX}PORT") or DEFAULT_PORT

        log_level: LogLevel
        if ns.log_level is not None:
            log_level = ns.log_level
        else:
            env_level = environ.get(f"{ENV_PREFIX}LOG_LEVEL")
            if env_level is None or env_level == "":
                log_level = DEFAULT_LOG_LEVEL
            elif env_level in _LOG_LEVELS:
                log_level = env_level
            else:
                raise SettingsError(
                    f"Invalid {ENV_PREFIX}LOG_LEVEL={env_level!r}; expected one of {_LOG_LEVELS}",
                )

        return cls(port=port, log_level=log_level)
