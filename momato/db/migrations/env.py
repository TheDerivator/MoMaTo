"""Alembic environment: migrates the database named in the config (or in MOMATO_ settings).

SQLite migrations run on a plain engine with foreign keys off (Alembic's batch mode recreates
tables), then `PRAGMA foreign_key_check` verifies nothing was broken.
"""

from alembic import context
from sqlalchemy import Connection, create_engine, make_url, pool

from momato.config import get_settings
from momato.db.models import Base
from momato.db.session import ensure_sqlite_directory

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().resolved_database_url


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _url()
    is_sqlite = make_url(url).get_backend_name() == "sqlite"
    ensure_sqlite_directory(url)
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        if is_sqlite:
            problems = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if problems:
                raise RuntimeError(f"migration left foreign key violations: {problems}")
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
