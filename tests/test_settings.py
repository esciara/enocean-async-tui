from __future__ import annotations

import pytest

from enocean_async_tui.settings import Settings, SettingsError


def test_defaults_when_no_args_and_empty_env() -> None:
    s = Settings.from_args([], env={})
    assert s.port == "/dev/ttyUSB0"
    assert s.log_level == "INFO"


def test_cli_port_override() -> None:
    s = Settings.from_args(["--port", "/dev/ttyACM0"], env={})
    assert s.port == "/dev/ttyACM0"


def test_env_port_override() -> None:
    s = Settings.from_args([], env={"ENOCEAN_TUI_PORT": "/dev/ttyACM1"})
    assert s.port == "/dev/ttyACM1"


def test_cli_wins_over_env() -> None:
    s = Settings.from_args(
        ["--port", "/dev/ttyACM0"],
        env={"ENOCEAN_TUI_PORT": "/dev/ttyACM1"},
    )
    assert s.port == "/dev/ttyACM0"


def test_cli_log_level_debug() -> None:
    s = Settings.from_args(["--log-level", "DEBUG"], env={})
    assert s.log_level == "DEBUG"


def test_env_log_level_warning() -> None:
    s = Settings.from_args([], env={"ENOCEAN_TUI_LOG_LEVEL": "WARNING"})
    assert s.log_level == "WARNING"


def test_invalid_env_log_level_raises() -> None:
    with pytest.raises(SettingsError):
        Settings.from_args([], env={"ENOCEAN_TUI_LOG_LEVEL": "YELL"})


def test_invalid_cli_log_level_systemexit() -> None:
    with pytest.raises(SystemExit):
        Settings.from_args(["--log-level", "YELL"], env={})


def test_empty_env_value_falls_back_to_default() -> None:
    s = Settings.from_args([], env={"ENOCEAN_TUI_PORT": "", "ENOCEAN_TUI_LOG_LEVEL": ""})
    assert s.port == "/dev/ttyUSB0"
    assert s.log_level == "INFO"


def test_settings_fake_flag() -> None:
    s = Settings.from_args(["--fake"], env={})
    assert s.fake is True


def test_settings_max_lines_default() -> None:
    s = Settings.from_args([], env={})
    assert s.max_lines == 10_000


def test_settings_max_lines_env() -> None:
    s = Settings.from_args([], env={"ENOCEAN_TUI_MAX_LINES": "500"})
    assert s.max_lines == 500


def test_settings_fake_wins_over_port(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    with caplog.at_level(logging.WARNING, logger="enocean_async_tui.settings"):
        s = Settings.from_args(["--fake", "--port", "/dev/ttyACM0"], env={})
    assert s.fake is True
    assert any("--port ignored" in r.message for r in caplog.records)
