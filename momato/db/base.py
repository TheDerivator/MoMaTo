"""Declarative base, constraint naming convention and portable column types (SQLite ↔ MS SQL)."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, override

from sqlalchemy import DateTime, Dialect, Enum, MetaData, TypeDecorator, Unicode, UnicodeText
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import DeclarativeBase

# Deterministic constraint names: Alembic migrations then look the same on every backend.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetimes in Python, stored as naive UTC (DATETIME2 on MS SQL).

    SQLite has no timezone support, so storing naive UTC everywhere keeps both backends identical.
    """

    impl = DateTime(timezone=False).with_variant(mssql.DATETIME2(), "mssql")  # not legacy DATETIME
    cache_ok = True

    @override
    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime: use datetime.now(UTC)")
        return value.astimezone(UTC).replace(tzinfo=None)

    @override
    def process_result_value(self, value: Any | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"expected a datetime from the database, got {type(value).__name__}")
        return value.replace(tzinfo=UTC)


def _enum_values(members: type[StrEnum]) -> list[str]:
    return [member.value for member in members]


def str_enum[E: StrEnum](enum: type[E], length: int = 20) -> Enum:
    """Store a StrEnum by value (`'progress'`) as VARCHAR.

    Values are validated in Python, not by a CHECK constraint: adding a member (a new status)
    then needs no migration, and Alembic doesn't render duplicate constraints.
    """
    return Enum(
        enum,
        native_enum=False,
        create_constraint=False,
        length=length,
        values_callable=_enum_values,
        validate_strings=True,
    )


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_email(email: str | None) -> str | None:
    """Emails are stored trimmed and lowercase (portability rule: case-insensitive uniqueness is
    normalised in code); blank means none."""
    if email is None or not email.strip():
        return None
    return email.strip().lower()


def normalize_username(username: str | None) -> str | None:
    if username is None or not username.strip():
        return None
    return username.strip().lower()


# Short aliases for column types, so models read cleanly and stay NVARCHAR on MS SQL.
Code = Unicode(20)
Key = Unicode(50)
ShortText = Unicode(100)
Name = Unicode(200)
Email = Unicode(254)
LongName = Unicode(300)
Text = UnicodeText().with_variant(mssql.NVARCHAR(None), "mssql")  # NVARCHAR(max), not NTEXT


class Base(DeclarativeBase):
    """Base class of every table."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
