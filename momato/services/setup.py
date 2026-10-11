"""Bring a database up to date: apply migrations, then create the built-in data."""

from momato.db.migrate import upgrade_database
from momato.db.session import Database
from momato.services.seed import SeedReport, seed_builtins


def prepare_database(
    database: Database, *, initial_admin_password: str | None = None
) -> SeedReport:
    """Migrate to the latest schema and create the rows the application needs (idempotent)."""
    upgrade_database(database.url)
    with database.session(write=True) as session:
        return seed_builtins(session, initial_admin_password=initial_admin_password)
