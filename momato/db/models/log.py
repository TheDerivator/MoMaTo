"""The logbook: one row per change of a core project field (LB-1)."""

from datetime import datetime

from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from momato.db.base import Base, Text, UTCDateTime, str_enum, utcnow
from momato.domain.logbook import LogField


class LogEntry(Base):
    """What changed, when and by whom; values are stored as shown to users."""

    __tablename__ = "log_entries"
    __table_args__ = (Index("ix_log_entries_project_at", "project_id", "at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    field_key: Mapped[LogField] = mapped_column(str_enum(LogField, 30))
    from_value: Mapped[str | None] = mapped_column(Text)
    to_value: Mapped[str | None] = mapped_column(Text)
    api_token_id: Mapped[int | None] = mapped_column(ForeignKey("api_tokens.id"))  # "via" (TOK-3)
