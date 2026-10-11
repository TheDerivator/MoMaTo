"""Booked time (whole minutes, D-038) and the weeks people have submitted (D-007)."""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from momato.db.base import Base, Key, UTCDateTime, utcnow


class TimeEntry(Base):
    """Minutes one person booked on one day on a project (a task, or *General*) or a category.

    Exactly one target: a project (optionally with a task of that project) or a category. The
    filtered unique indexes keep one row per person, day and target, also for rows without a task.
    """

    __tablename__ = "time_entries"
    __table_args__ = (
        # A task must belong to the booking's project (null task: not checked, i.e. *General*).
        ForeignKeyConstraint(
            ["task_id", "project_id"],
            ["tasks.id", "tasks.project_id"],
            name="fk_time_entries_task_same_project",
        ),
        CheckConstraint(
            "(project_id IS NOT NULL AND category_key IS NULL)"
            " OR (project_id IS NULL AND category_key IS NOT NULL AND task_id IS NULL)",
            name="exactly_one_target",
        ),
        CheckConstraint("minutes >= 0", name="minutes_not_negative"),
        Index("ix_time_entries_user_date", "user_id", "work_date"),
        Index("ix_time_entries_project_date", "project_id", "work_date"),
        Index(
            "uq_time_entries_task_cell",
            "user_id",
            "work_date",
            "project_id",
            "task_id",
            unique=True,
            sqlite_where=text("task_id IS NOT NULL"),
            mssql_where=text("task_id IS NOT NULL"),
        ),
        Index(
            "uq_time_entries_general_cell",
            "user_id",
            "work_date",
            "project_id",
            unique=True,
            sqlite_where=text("project_id IS NOT NULL AND task_id IS NULL"),
            mssql_where=text("project_id IS NOT NULL AND task_id IS NULL"),
        ),
        Index(
            "uq_time_entries_category_cell",
            "user_id",
            "work_date",
            "category_key",
            unique=True,
            sqlite_where=text("category_key IS NOT NULL"),
            mssql_where=text("category_key IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    work_date: Mapped[date]
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    task_id: Mapped[int | None]
    category_key: Mapped[str | None] = mapped_column(Key)  # a profile category (D-009)
    minutes: Mapped[int]
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    api_token_id: Mapped[int | None] = mapped_column(ForeignKey("api_tokens.id"))  # "via"


class WeekSubmission(Base):
    """A soft marker: the person says their week is complete (D-007). No lock, no approval."""

    __tablename__ = "week_submissions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    iso_year: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    iso_week: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
