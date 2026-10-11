"""Shared pytest fixtures: isolated settings, an HTTP client, and the MS SQL portability guard.

The clock is fixed: tests pin `MOMATO_TODAY` to Thursday 8 October 2026 (ISO week 41), the design's
date, so expected values never depend on when the suite runs.

A template database is migrated once per test run; each test gets its own copy (a file copy is
much faster than running the migrations again).

With `MOMATO_TEST_DATABASE_URL` set (an empty MS SQL database, to prove portability) the database
suites use that database instead: it is migrated once and emptied before every test. Tests about
SQLite itself are skipped then (`requires_sqlite`).
"""

import os
import shutil
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

from momato.config import Environment, Settings
from momato.db.base import Base
from momato.db.session import Database
from momato.services.profile import load_profile
from momato.services.sample_data import Sample, build_sample, load_sample_data
from momato.services.setup import prepare_database
from momato.web import create_app
from momato.web.csrf import CSRF_COOKIE, CSRF_HEADER

# "Today" in the design's sample data; tests pin the server's date to it.
SAMPLE_TODAY = date(2026, 10, 8)
DB_FILENAME = "momato.sqlite3"
TEST_ADMIN_PASSWORD = "admin-password-for-tests"
DEMO_PASSWORD = "demo-password-for-tests"  # every sample person signs in with it

MSSQL_MAX_PARAMETERS = 2100


@event.listens_for(Engine, "before_cursor_execute")
def _portable_parameter_count(
    conn: object,
    cursor: object,
    statement: str,
    parameters: object,
    context: object,
    executemany: bool,
) -> None:
    """MS SQL refuses a statement with more than 2,100 parameters, SQLite takes 32,766: fail any
    test that sends more, so big id lists cannot pass here and break there. (Bulk INSERTs are
    left out: SQLAlchemy sizes their batches per database.)"""
    if executemany or statement.lstrip()[:6].upper() == "INSERT":
        return
    count = len(parameters) if isinstance(parameters, tuple | list | dict) else 0
    assert count <= MSSQL_MAX_PARAMETERS, (
        f"{count} parameters (MS SQL takes {MSSQL_MAX_PARAMETERS})"
    )


EXTERNAL_DATABASE_URL = os.environ.get("MOMATO_TEST_DATABASE_URL") or None

requires_sqlite = pytest.mark.skipif(
    EXTERNAL_DATABASE_URL is not None and not EXTERNAL_DATABASE_URL.startswith("sqlite"),
    reason="about SQLite itself",
)


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def prepare(url: str) -> None:
    """Migrate and create the built-in rows."""
    database = Database(url)
    prepare_database(database, initial_admin_password=TEST_ADMIN_PASSWORD)
    database.dispose()  # for SQLite: closing the last connection checkpoints the WAL


def empty_database(url: str) -> None:
    """Delete every row (children first); the schema and its migration version stay."""
    engine = create_engine(url)
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    engine.dispose()


@pytest.fixture(scope="session")
def template_db(tmp_path_factory: pytest.TempPathFactory) -> Path | None:
    if EXTERNAL_DATABASE_URL:
        prepare(EXTERNAL_DATABASE_URL)
        return None
    path = tmp_path_factory.mktemp("template") / DB_FILENAME
    prepare(sqlite_url(path))
    return path


@pytest.fixture
def settings(tmp_path: Path, template_db: Path | None) -> Settings:
    """Settings pointing at a fresh copy of the template database in a temporary data dir."""
    if template_db is None:
        assert EXTERNAL_DATABASE_URL
        empty_database(EXTERNAL_DATABASE_URL)
        prepare(EXTERNAL_DATABASE_URL)
    else:
        shutil.copyfile(template_db, tmp_path / DB_FILENAME)
    return _settings(tmp_path)


def _settings(data_dir: Path) -> Settings:
    return Settings(
        environment=Environment.TEST,
        data_dir=data_dir,
        database_url=EXTERNAL_DATABASE_URL,
        initial_admin_password=SecretStr(TEST_ADMIN_PASSWORD),
        today=SAMPLE_TODAY,
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )


def _load_sample(settings: Settings) -> None:
    database = Database(settings.resolved_database_url)
    with database.session(write=True) as session:
        assert load_sample_data(
            session,
            today=SAMPLE_TODAY,
            profile=load_profile(settings.profile),
            uploads_dir=settings.uploads_dir,
            demo_password=DEMO_PASSWORD,
        )
    database.dispose()


@pytest.fixture(scope="session")
def sample_template_dir(
    template_db: Path | None, tmp_path_factory: pytest.TempPathFactory
) -> Path | None:
    """A data dir with the sample data loaded (database file and uploaded pictures), built once.
    None with an external database: there every test loads the sample itself."""
    if template_db is None:
        return None
    folder = tmp_path_factory.mktemp("sample-template")
    shutil.copyfile(template_db, folder / DB_FILENAME)
    _load_sample(_settings(folder))
    return folder


@pytest.fixture(scope="session")
def sample() -> Sample:
    """The sample's specs for the pinned date: what the loaded database must equal."""
    return build_sample(SAMPLE_TODAY, load_profile("default"))


@pytest.fixture
def sample_settings(tmp_path: Path, sample_template_dir: Path | None) -> Settings:
    """Settings pointing at a fresh copy of the database with the sample data loaded."""
    if sample_template_dir is None:
        assert EXTERNAL_DATABASE_URL
        empty_database(EXTERNAL_DATABASE_URL)
        prepare(EXTERNAL_DATABASE_URL)
        settings = _settings(tmp_path)
        _load_sample(settings)
        return settings
    shutil.copytree(sample_template_dir, tmp_path, dirs_exist_ok=True)
    return _settings(tmp_path)


@pytest.fixture
def sample_database(sample_settings: Settings) -> Iterator[Database]:
    db = Database(sample_settings.resolved_database_url)
    yield db
    db.dispose()


@pytest.fixture
def database(settings: Settings) -> Iterator[Database]:
    db = Database(settings.resolved_database_url)
    yield db
    db.dispose()


@pytest.fixture
def session(database: Database) -> Iterator[Session]:
    """A write session; the test decides when to commit."""
    with database.new_session(write=True) as s:
        yield s


def start_client(app: FastAPI) -> Iterator[TestClient]:
    """A client that behaves like the frontend: it echoes the CSRF cookie in the header."""
    with TestClient(app) as test_client:
        test_client.get("/api/health")  # receive the CSRF cookie
        test_client.headers[CSRF_HEADER] = test_client.cookies[CSRF_COOKIE]
        yield test_client


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    yield from start_client(create_app(settings))


@pytest.fixture
def sample_client(sample_settings: Settings) -> Iterator[TestClient]:
    """The frontend-like client on a database with the sample data."""
    yield from start_client(create_app(sample_settings))
