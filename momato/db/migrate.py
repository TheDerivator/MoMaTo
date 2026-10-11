"""Run Alembic programmatically: upgrade to the latest schema, check models against migrations.

Used by the CLI (`python -m momato db upgrade`), by application startup and by the tests, so no
`alembic.ini` is needed at runtime. Developers create revisions with `uv run alembic revision
--autogenerate -m "..."` (that uses the root `alembic.ini`).
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util import CommandError
from sqlalchemy import create_engine

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def alembic_config(url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))  # configparser escaping
    return config


def upgrade_database(url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def check_models_match_migrations(url: str) -> None:
    """Raise if the models contain changes that no migration covers (`alembic check`)."""
    command.check(alembic_config(url))


def current_revision(url: str) -> str | None:
    """The schema revision a database is at (None: not created by MoMaTo's migrations)."""
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def is_known_revision(revision: str) -> bool:
    """Whether this version of MoMaTo has the migration (False: made by a newer version)."""
    try:
        ScriptDirectory.from_config(alembic_config("sqlite://")).get_revision(revision)
    except CommandError:  # "Can't locate revision ..."
        return False
    return True
