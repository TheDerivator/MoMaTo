"""Remarks: posts and replies (one level), their edit history and attached images (D-015)."""

from datetime import datetime

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from momato.db.base import Base, Name, ShortText, Text, UTCDateTime, utcnow


class Post(Base):
    """A remark (no parent) or a reply (parent: a remark of the same project)."""

    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint("id", "project_id"),  # target of the same-project foreign keys
        ForeignKeyConstraint(
            ["parent_id", "project_id"],
            ["posts.id", "posts.project_id"],
            name="fk_posts_parent_same_project",
        ),
        Index("ix_posts_project_created", "project_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    parent_id: Mapped[int | None]
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body_md: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    edited_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    edited_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # A deleted remark that has replies stays as "Remark deleted" (RM-5).
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # The API tokens it was written and last edited through ("via", TOK-3).
    api_token_id: Mapped[int | None] = mapped_column(ForeignKey("api_tokens.id"))
    edited_api_token_id: Mapped[int | None] = mapped_column(ForeignKey("api_tokens.id"))


class PostRevision(Base):
    """An earlier text of an edited post, kept so it can be viewed (RM-5)."""

    __tablename__ = "post_revisions"

    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), primary_key=True)
    rev: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    body_md: Mapped[str] = mapped_column(Text)
    written_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    written_at: Mapped[datetime] = mapped_column(UTCDateTime)
    api_token_id: Mapped[int | None] = mapped_column(ForeignKey("api_tokens.id"))


class Attachment(Base):
    """An image of a remark. Uploaded as a draft (no post) until the remark is posted (RM-2)."""

    __tablename__ = "attachments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["post_id", "project_id"],
            ["posts.id", "posts.project_id"],
            name="fk_attachments_post_same_project",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    post_id: Mapped[int | None]
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(Name)
    content_type: Mapped[str] = mapped_column(ShortText)
    size: Mapped[int]
    # 32 hex digits: the file's name in the uploads folder and its address (api/attachments/<id>/…)
    public_id: Mapped[str] = mapped_column(ShortText, unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
