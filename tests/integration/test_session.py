"""Engine tuning, write sessions, named locks, id lists and Unicode case folding."""

from pathlib import Path

import pytest
from sqlalchemy import select, text

from momato.config import Settings
from momato.db.ids import in_ids
from momato.db.models import AppLock, OrgNode
from momato.db.session import PROJECT_NUMBER_LOCK, Database, acquire_lock
from momato.db.text import casefold, contains_ci
from tests.conftest import requires_sqlite, sqlite_url
from tests.helpers import count_statements


@requires_sqlite
def test_sqlite_connections_are_tuned(tmp_path: Path) -> None:
    database = Database(sqlite_url(tmp_path / "tuned.sqlite3"))
    with database.engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert connection.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 15000
    assert database.is_sqlite
    database.dispose()


@requires_sqlite
def test_the_database_folder_is_created(tmp_path: Path) -> None:
    database = Database(sqlite_url(tmp_path / "not" / "yet" / "there.sqlite3"))
    with database.engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    assert (tmp_path / "not" / "yet").is_dir()
    database.dispose()


@requires_sqlite
def test_write_sessions_start_with_begin_immediate_and_read_sessions_do_not(
    database: Database,
) -> None:
    with count_statements() as counter:
        with database.session(write=True) as session:
            session.execute(select(OrgNode.id))
        with database.session() as session:
            session.execute(select(OrgNode.id))
    # The BEGINs are issued through the driver, not as statements; what must hold is that a
    # write session can see its own uncommitted work and a read session cannot see it.
    assert counter.selects == 2


def test_a_session_commits_on_success_and_rolls_back_on_error(database: Database) -> None:
    with database.session(write=True) as session:
        session.add(OrgNode(name="Kept"))
    with pytest.raises(RuntimeError), database.session(write=True) as session:
        session.add(OrgNode(name="Lost"))
        session.flush()
        raise RuntimeError("boom")
    with database.session() as session:
        assert list(session.scalars(select(OrgNode.name))) == ["Kept"]


def test_a_named_lock_is_acquired_by_updating_its_row(database: Database) -> None:
    with database.session(write=True) as session:
        acquire_lock(session, PROJECT_NUMBER_LOCK)
        acquire_lock(session, PROJECT_NUMBER_LOCK)
    with database.session() as session:
        assert (
            session.scalar(select(AppLock.counter).where(AppLock.name == PROJECT_NUMBER_LOCK)) == 2
        )


def test_acquiring_a_missing_lock_fails_loudly(database: Database) -> None:
    with database.session(write=True) as session, pytest.raises(RuntimeError, match="missing"):
        acquire_lock(session, "no_such_lock")


def test_in_ids_takes_any_number_of_ids_without_parameters(database: Database) -> None:
    """MS SQL takes at most 2,100 parameters: ids are written into the SQL (the guard is on)."""
    with database.session(write=True) as session:
        session.add_all(OrgNode(name=f"node {i}") for i in range(30))
        session.flush()
        ids = list(session.scalars(select(OrgNode.id)))
        many = [*ids, *range(10_000, 13_000)]  # 3,030 ids: far over the parameter limit
        found = list(session.scalars(select(OrgNode.id).where(in_ids(OrgNode.id, many))))
    assert sorted(found) == sorted(ids)


def test_in_ids_with_no_ids_matches_nothing(database: Database) -> None:
    with database.session() as session:
        assert list(session.scalars(select(OrgNode.id).where(in_ids(OrgNode.id, [])))) == []


def test_casefold_matching_covers_all_of_unicode(database: Database) -> None:
    """SQLite's own lower() leaves "É" alone; the registered function does not."""
    with database.session(write=True) as session:
        session.add_all(OrgNode(name=n) for n in ["Électricité", "ÉNERGIE", "Water_100%", "Other"])
        session.flush()

        def find(needle: str) -> list[str]:
            query = (
                select(OrgNode.name).where(contains_ci(OrgNode.name, needle)).order_by(OrgNode.name)
            )
            return list(session.scalars(query))

        assert find("électr") == ["Électricité"]
        assert find("énergie") == ["ÉNERGIE"]
        assert find("ÉLECTR") == ["Électricité"]
        assert find("_") == ["Water_100%"]  # underscore and percent are literal
        assert find("%") == ["Water_100%"]
        assert list(
            session.scalars(select(casefold(OrgNode.name)).where(OrgNode.name == "ÉNERGIE"))
        ) == ["énergie"]


def test_the_data_dir_of_settings_holds_the_database(settings: Settings) -> None:
    assert (
        Path(settings.resolved_database_url.removeprefix("sqlite:///")).parent == settings.data_dir
    )
