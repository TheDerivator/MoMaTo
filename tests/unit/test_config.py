"""Settings: defaults, the MOMATO_ prefix, the base path, the pinned date."""

from datetime import date
from pathlib import Path

import pytest

from momato.config import PROJECT_ROOT, Environment, Settings, get_settings


def make(**values: object) -> Settings:
    return Settings(_env_file=None, **values)  # pyright: ignore[reportCallIssue, reportArgumentType]


def test_defaults() -> None:
    settings = make()
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.data_dir == PROJECT_ROOT / "var"
    assert settings.auto_migrate is True
    assert (settings.host, settings.port) == ("127.0.0.1", 8000)
    assert settings.today is None


def test_values_come_from_prefixed_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOMATO_PORT", "9123")
    monkeypatch.setenv("MOMATO_ENVIRONMENT", "production")
    monkeypatch.setenv("MOMATO_AUTO_MIGRATE", "false")
    monkeypatch.setenv("PORT", "1")  # unprefixed variables are not ours
    settings = make()
    assert settings.port == 9123
    assert settings.environment is Environment.PRODUCTION
    assert settings.auto_migrate is False


def test_the_app_folders_env_file_is_read(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("MOMATO_PORT=8123\nSOMETHING_ELSE=1\n", encoding="utf-8")
    assert Settings(_env_file=env_file).port == 8123  # pyright: ignore[reportCallIssue]


def test_database_defaults_to_sqlite_in_the_data_dir(tmp_path: Path) -> None:
    settings = make(data_dir=tmp_path)
    assert settings.resolved_database_url == f"sqlite:///{(tmp_path / 'momato.sqlite3').as_posix()}"
    assert settings.uploads_dir == tmp_path / "uploads"


def test_an_explicit_database_url_wins(tmp_path: Path) -> None:
    url = "mssql+pyodbc://user:pw@host/momato?driver=ODBC+Driver+18+for+SQL+Server"
    assert make(data_dir=tmp_path, database_url=url).resolved_database_url == url


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("/", "/"),
        ("", "/"),
        ("momato", "/momato/"),
        ("/momato", "/momato/"),
        ("/momato/", "/momato/"),
        ("  /tools/momato/  ", "/tools/momato/"),
        ("///", "/"),
    ],
)
def test_the_base_path_has_one_leading_and_one_trailing_slash(
    configured: str, expected: str
) -> None:
    assert make(base_path=configured).normalized_base_path == expected


def test_today_can_be_pinned() -> None:
    assert make(today=date(2026, 10, 8)).current_date() == date(2026, 10, 8)


def test_today_is_the_servers_date_when_not_pinned() -> None:
    assert make().current_date() == date.today()


def test_settings_are_created_once_per_process() -> None:
    assert get_settings() is get_settings()
