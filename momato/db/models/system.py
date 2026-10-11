"""Infrastructure tables: named lock rows (see db/session.py) and one-time setup markers."""

from sqlalchemy import Unicode
from sqlalchemy.orm import Mapped, mapped_column

from momato.db.base import Base


class AppLock(Base):
    """One row per named lock. Updating the row holds a write lock on it until commit."""

    __tablename__ = "app_locks"

    name: Mapped[str] = mapped_column(Unicode(50), primary_key=True)
    counter: Mapped[int] = mapped_column(default=0)


class AppState(Base):
    """Facts about this installation that must survive restarts, e.g. that the default grants
    were created (so an administrator removing one is not undone at the next start)."""

    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(Unicode(50), primary_key=True)
    value: Mapped[str] = mapped_column(Unicode(200))
