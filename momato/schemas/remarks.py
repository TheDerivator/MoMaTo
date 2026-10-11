"""Shapes of the remark endpoints: remarks with their replies, earlier versions, attachments,
Markdown preview (RM-1 – RM-5)."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from momato.schemas.projects import PersonRef

Body = Annotated[str, StringConstraints(max_length=20_000)]


class RemarkOut(BaseModel):
    """A remark (no `parent_id`, carries its `replies`) or a reply (one level only)."""

    id: int
    parent_id: int | None
    author: PersonRef | None  # None for a deleted remark that stays because of its replies
    created_at: datetime
    edited_at: datetime | None
    via: str | None = None  # the API token it was written through (TOK-3)
    edited_via: str | None = None
    versions: int  # more than 1: earlier versions are kept (GET /api/remarks/{id}/history)
    deleted: bool
    body_md: str
    html: str  # sanitized; safe to insert as-is
    can_edit: bool  # the author, who may still comment
    can_delete: bool  # the author, or someone who manages users
    replies: list[RemarkOut]  # oldest first; empty on a reply


class RemarkList(BaseModel):
    items: list[RemarkOut]  # newest first
    count: int  # remarks, not counting replies or "Remark deleted" placeholders
    can_comment: bool


class RemarkVersion(BaseModel):
    """One version of a remark as it was written; the last one is the remark as it is now."""

    rev: int
    written_by: PersonRef
    written_at: datetime
    via: str | None = None
    body_md: str
    html: str


class RemarkCreate(BaseModel):
    body_md: Body


class RemarkUpdate(BaseModel):
    body_md: Body


class AttachmentOut(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int
    url: str  # relative to the app's base path, e.g. "api/attachments/<id>/map.png"
    markdown: str  # ready to insert: ![map.png](api/attachments/<id>/map.png)


class MarkdownPreviewIn(BaseModel):
    body_md: Body


class MarkdownPreviewOut(BaseModel):
    html: str
