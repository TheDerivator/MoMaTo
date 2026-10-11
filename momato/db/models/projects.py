"""Projects, their members, detail values, tasks (gantt rows) and planned days (D-009, D-034)."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from momato.db.base import Base, Key, Name, Text, UTCDateTime, str_enum, utcnow
from momato.domain.projects import DEFAULT_PRIORITY, Priority, ProjectStatus


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        # The project list: a branch's projects by status, newest number first (keyset paging).
        Index("ix_projects_node_status_number", "org_node_id", "status", "number"),
        CheckConstraint("end_date >= start_date", name="dates_in_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(unique=True)  # the permalink; assigned by the server
    name: Mapped[str] = mapped_column(Name)
    org_node_id: Mapped[int] = mapped_column(ForeignKey("org_nodes.id"))
    status: Mapped[ProjectStatus] = mapped_column(
        str_enum(ProjectStatus), default=ProjectStatus.IDEA
    )
    coordinator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    start_date: Mapped[date]
    end_date: Mapped[date]
    goal: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[Priority] = mapped_column(str_enum(Priority), default=DEFAULT_PRIORITY)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    version: Mapped[int] = mapped_column(default=1)  # optimistic locking (PP-6)


class ProjectMember(Base):
    """A person involved in a project; the coordinator is always one (PD-4)."""

    __tablename__ = "project_members"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)


class ProjectDetail(Base):
    """One detail value, JSON-encoded, validated against the profile (D-034)."""

    __tablename__ = "project_details"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    field_key: Mapped[str] = mapped_column(Key, primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Task(Base):
    """A row of the project's gantt planning (also called a phase)."""

    __tablename__ = "tasks"
    __table_args__ = (
        # Target of the composite foreign key that makes a time entry's task belong to its project.
        UniqueConstraint("id", "project_id"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="progress_range"),
        CheckConstraint("planned_end >= planned_start", name="dates_in_order"),
        CheckConstraint(
            "revised_end IS NULL OR revised_end > planned_end", name="revised_after_end"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    position: Mapped[int] = mapped_column(default=0)
    name: Mapped[str] = mapped_column(Name)
    planned_start: Mapped[date]
    planned_end: Mapped[date]
    revised_end: Mapped[date | None]
    is_milestone: Mapped[bool] = mapped_column(default=False)
    progress: Mapped[int] = mapped_column(default=0)  # entered by hand, 0 to 100 (D-008)
    version: Mapped[int] = mapped_column(default=1)


class PlannedDays(Base):
    """Days planned for one member on one project in one calendar quarter (a cell of PD-1)."""

    __tablename__ = "planned_days"
    __table_args__ = (
        # Only members have planned days; removing a member removes theirs first (PD-4).
        ForeignKeyConstraint(
            ["project_id", "user_id"],
            ["project_members.project_id", "project_members.user_id"],
            name="fk_planned_days_member",
        ),
        CheckConstraint("days >= 0", name="days_not_negative"),
        # A person's planning across projects (People planning, M8).
        Index("ix_planned_days_user_quarter", "user_id", "quarter_start"),
    )

    project_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(primary_key=True)
    quarter_start: Mapped[date] = mapped_column(primary_key=True)  # the quarter's first day
    days: Mapped[Decimal] = mapped_column(Numeric(6, 2))  # steps of 0.5; never a float
