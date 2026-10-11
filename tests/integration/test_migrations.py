"""Migrations build the whole schema, match the models exactly, and can be rolled back."""

from pathlib import Path

from alembic import command
from sqlalchemy import inspect, text

from momato.db.migrate import (
    alembic_config,
    check_models_match_migrations,
    current_revision,
    is_known_revision,
    upgrade_database,
)
from momato.db.models import Base
from momato.db.session import Database
from momato.services.setup import prepare_database
from tests.conftest import TEST_ADMIN_PASSWORD, requires_sqlite, sqlite_url


@requires_sqlite
def test_upgrading_an_empty_database_creates_every_table(tmp_path: Path) -> None:
    url = sqlite_url(tmp_path / "fresh.sqlite3")
    upgrade_database(url)
    database = Database(url)
    tables = set(inspect(database.engine).get_table_names())
    database.dispose()
    assert set(Base.metadata.tables) <= tables


@requires_sqlite
def test_models_and_migrations_agree(tmp_path: Path) -> None:
    """Fails when a model changed without a migration (run alembic revision --autogenerate)."""
    url = sqlite_url(tmp_path / "fresh.sqlite3")
    upgrade_database(url)
    check_models_match_migrations(url)


@requires_sqlite
def test_downgrade_to_base_and_back(tmp_path: Path) -> None:
    url = sqlite_url(tmp_path / "fresh.sqlite3")
    upgrade_database(url)
    command.downgrade(alembic_config(url), "base")
    database = Database(url)
    with database.engine.connect() as connection:
        left = set(inspect(connection).get_table_names()) - {"alembic_version"}
    database.dispose()
    assert left == set()
    upgrade_database(url)
    check_models_match_migrations(url)


@requires_sqlite
def test_upgrading_twice_changes_nothing(tmp_path: Path) -> None:
    url = sqlite_url(tmp_path / "fresh.sqlite3")
    upgrade_database(url)
    first = current_revision(url)
    upgrade_database(url)
    assert current_revision(url) == first
    assert first is not None
    assert is_known_revision(first)
    assert not is_known_revision("0123456789ab")


@requires_sqlite
def test_the_migration_leaves_the_indexes_of_the_hot_paths(tmp_path: Path) -> None:
    """REQUIREMENTS section 5: projects by (node, status, number), time by (user, date) and
    (project, date), planned days by (user, quarter)."""
    url = sqlite_url(tmp_path / "fresh.sqlite3")
    upgrade_database(url)
    database = Database(url)
    inspector = inspect(database.engine)

    def indexed(table: str) -> list[list[str | None]]:
        return [list(ix["column_names"]) for ix in inspector.get_indexes(table)]

    assert ["org_node_id", "status", "number"] in indexed("projects")
    assert ["user_id", "work_date"] in indexed("time_entries")
    assert ["project_id", "work_date"] in indexed("time_entries")
    assert ["user_id", "quarter_start"] in indexed("planned_days")
    unique = {tuple(c["column_names"]) for c in inspector.get_unique_constraints("projects")}
    assert ("number",) in unique
    database.dispose()


def test_preparing_a_database_is_idempotent(database: Database) -> None:
    first = prepare_database(database, initial_admin_password=TEST_ADMIN_PASSWORD)
    second = prepare_database(database, initial_admin_password=TEST_ADMIN_PASSWORD)
    assert first.created == []  # the template database was prepared already
    assert second.created == []
    with database.session() as session:
        assert session.execute(text("SELECT COUNT(*) FROM app_locks")).scalar_one() == 1
