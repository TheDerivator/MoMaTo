"""People: one record per person, who may or may not sign in (D-012), and their availability."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, Numeric, Unicode, text
from sqlalchemy.orm import Mapped, mapped_column, validates

from momato.db.base import (
    Base,
    Email,
    Name,
    ShortText,
    UTCDateTime,
    normalize_email,
    normalize_username,
    str_enum,
    utcnow,
)


class UserKind(StrEnum):
    PERSON = "person"
    SYSTEM = "system"  # the built-in `admin` and `anonymous`: not people (D-012)


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"  # cannot sign in; still a person
    DEACTIVATED = "deactivated"  # left: out of pickers and planning, history kept (ADM-2)


class User(Base):
    """A person, or a system account (`admin`, `anonymous`); sign-in is optional (D-012).

    Username and email are stored lowercase and unique when present (filtered unique indexes:
    MS SQL's UNIQUE would allow only one NULL).
    """

    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_username",
            "username",
            unique=True,
            sqlite_where=text("username IS NOT NULL"),
            mssql_where=text("username IS NOT NULL"),
        ),
        Index(
            "uq_users_email",
            "email",
            unique=True,
            sqlite_where=text("email IS NOT NULL"),
            mssql_where=text("email IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[UserKind] = mapped_column(str_enum(UserKind), default=UserKind.PERSON)
    name: Mapped[str] = mapped_column(Name)
    job_title: Mapped[str | None] = mapped_column(ShortText)
    org_node_id: Mapped[int | None] = mapped_column(ForeignKey("org_nodes.id"), index=True)
    hue: Mapped[int] = mapped_column(default=285)  # the person's avatar colour (0-359)
    # The work pattern: minutes per weekday (D-019). Default eight hours, Monday to Friday.
    work_minutes_mon: Mapped[int] = mapped_column(default=480)
    work_minutes_tue: Mapped[int] = mapped_column(default=480)
    work_minutes_wed: Mapped[int] = mapped_column(default=480)
    work_minutes_thu: Mapped[int] = mapped_column(default=480)
    work_minutes_fri: Mapped[int] = mapped_column(default=480)
    status: Mapped[UserStatus] = mapped_column(str_enum(UserStatus), default=UserStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # Sign-in. A local password (argon2), a prepared email or Windows login name for SSO, or none.
    username: Mapped[str | None] = mapped_column(ShortText)
    email: Mapped[str | None] = mapped_column(Email)
    password_hash: Mapped[str | None] = mapped_column(Unicode(255))
    must_change_password: Mapped[bool] = mapped_column(default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    @validates("username")
    def _normalize_username(self, _key: str, value: str | None) -> str | None:
        return normalize_username(value)

    @validates("email")
    def _normalize_email(self, _key: str, value: str | None) -> str | None:
        return normalize_email(value)


class Availability(Base):
    """Days a person can be planned in a year when it differs from the profile default (D-020)."""

    __tablename__ = "availability"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    year: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    days: Mapped[Decimal] = mapped_column(Numeric(6, 2))
