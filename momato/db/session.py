"""Engine and session factory, SQLite connection tuning, and portable named locks.

Transactions: on SQLite we take over `BEGIN` from the Python driver (which otherwise delays it
until the first write, letting a read-then-write interleave with another writer). Sessions opened
with `write=True` start with `BEGIN IMMEDIATE`, so write requests are serialized while reads stay
concurrent (WAL). On other backends the default isolation applies, and `acquire_lock` serializes
critical sections such as assigning the next project number.
"""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from sqlalchemy import Connection, CursorResult, Engine, create_engine, event, make_url, update
from sqlalchemy.orm import Session, sessionmaker

from momato.db.models.system import AppLock
from momato.db.text import SQLITE_CASEFOLD_FUNCTION, sqlite_casefold

_WRITE_OPTION = "momato_write"

# Names of the locks that exist (rows are created by the setup).
PROJECT_NUMBER_LOCK = "project_numbers"  # the next free project number (R4.7)
LOCK_NAMES = (PROJECT_NUMBER_LOCK,)


def acquire_lock(session: Session, name: str) -> None:
    """Serialize a critical section across processes until the transaction ends."""
    result = session.execute(
        update(AppLock).where(AppLock.name == name).values(counter=AppLock.counter + 1)
    )
    if cast(CursorResult[Any], result).rowcount != 1:
        raise RuntimeError(f"lock row {name!r} is missing: run the seed")


def _is_sqlite(url: str) -> bool:
    return make_url(url).get_backend_name() == "sqlite"


def ensure_sqlite_directory(url: str) -> None:
    """Create the folder of a file-based SQLite database; no-op for other URLs."""
    if _is_sqlite(url):
        database = make_url(url).database
        if database and database != ":memory:":
            Path(database).parent.mkdir(parents=True, exist_ok=True)


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:  # pyright: ignore[reportUnusedFunction]
        dbapi_connection.isolation_level = None  # we emit BEGIN ourselves (see module docstring)
        dbapi_connection.create_function(
            SQLITE_CASEFOLD_FUNCTION, 1, sqlite_casefold, deterministic=True
        )
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(connection: Connection) -> None:  # pyright: ignore[reportUnusedFunction]
        write = connection.get_execution_options().get(_WRITE_OPTION, False)
        connection.exec_driver_sql("BEGIN IMMEDIATE" if write else "BEGIN")


def create_db_engine(url: str) -> Engine:
    """An engine for `url`; SQLite gets its directory created and its connections tuned."""
    if _is_sqlite(url):
        ensure_sqlite_directory(url)
        engine = create_engine(url)
        _configure_sqlite(engine)
        return engine
    return create_engine(url, pool_pre_ping=True)


class Database:
    """Owns the engine and hands out sessions. One instance per application."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.engine = create_db_engine(url)
        write_engine = self.engine.execution_options(**{_WRITE_OPTION: True})
        self._read = sessionmaker(self.engine, expire_on_commit=False)
        self._write = sessionmaker(write_engine, expire_on_commit=False)

    @property
    def is_sqlite(self) -> bool:
        return _is_sqlite(self.url)

    def new_session(self, *, write: bool = False) -> Session:
        return (self._write if write else self._read)()

    @contextmanager
    def session(self, *, write: bool = False) -> Generator[Session]:
        """A session that commits on success and rolls back on error."""
        with self.new_session(write=write) as session:
            try:
                yield session
                session.commit()
            except BaseException:
                session.rollback()
                raise

    def dispose(self) -> None:
        self.engine.dispose()
