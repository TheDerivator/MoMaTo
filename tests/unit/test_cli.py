"""The command line: parsing and what `serve` hands to uvicorn."""

import runpy
import sys
from pathlib import Path
from typing import Any

import pytest

from momato import cli
from momato.config import get_settings


def test_a_command_is_required() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.build_parser().parse_args([])
    assert exit_info.value.code == 2


def test_serve_defaults_come_from_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr("uvicorn.run", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setenv("MOMATO_HOST", "0.0.0.0")  # noqa: S104
    monkeypatch.setenv("MOMATO_PORT", "8765")
    get_settings.cache_clear()
    try:
        assert cli.main(["serve"]) == 0
    finally:
        get_settings.cache_clear()
    [(args, kwargs)] = calls
    assert args == ("momato.web:create_app",)
    assert kwargs["factory"] is True
    assert (kwargs["host"], kwargs["port"], kwargs["reload"]) == ("0.0.0.0", 8765, False)  # noqa: S104
    assert kwargs["proxy_headers"] is False


def test_python_dash_m_momato_runs_the_command_line(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr("uvicorn.run", lambda *_a, **kw: calls.append(kw))
    monkeypatch.setattr(sys, "argv", ["momato", "serve", "--port", "9002"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("momato", run_name="__main__")
    assert exit_info.value.code == 0
    assert calls[0]["port"] == 9002


def test_serve_options_override_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr("uvicorn.run", lambda *_a, **kw: calls.append(kw))
    assert cli.main(["serve", "--host", "127.0.0.2", "--port", "9001", "--reload"]) == 0
    [kwargs] = calls
    assert (kwargs["host"], kwargs["port"], kwargs["reload"]) == ("127.0.0.2", 9001, True)


def test_db_upgrade_and_seed_create_and_fill_a_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("MOMATO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MOMATO_TODAY", "2026-10-08")
    get_settings.cache_clear()
    try:
        assert cli.main(["db", "upgrade"]) == 0
        assert "up to date" in capsys.readouterr().out
        assert (tmp_path / "momato.sqlite3").is_file()

        assert cli.main(["seed"]) == 0
        assert "created lock project_numbers" in capsys.readouterr().out
        assert cli.main(["seed"]) == 0  # nothing left to create
        assert "created" not in capsys.readouterr().out

        assert cli.main(["seed", "--sample"]) == 0
        assert "Loaded the sample data." in capsys.readouterr().out
        assert cli.main(["seed", "--sample"]) == 0
        assert "already holds projects" in capsys.readouterr().out
    finally:
        get_settings.cache_clear()
    assert any((tmp_path / "uploads").iterdir())  # the sample's pictures


def test_seed_refuses_a_broken_profile(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("MOMATO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MOMATO_PROFILE", "no-such-profile")
    get_settings.cache_clear()
    try:
        assert cli.main(["seed", "--sample"]) == 1
    finally:
        get_settings.cache_clear()
    assert "Cannot seed: profile 'no-such-profile' does not exist" in capsys.readouterr().out
    assert not (tmp_path / "momato.sqlite3").exists()  # nothing was touched
