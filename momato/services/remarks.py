"""Remarks and replies of a project (RM-1 – RM-5): list, post, reply, edit with history, delete,
and the images they refer to.

Reading needs the right to view the project, posting `project.comment` (coordinators and members
have it implicitly, D-014). Authors edit and delete their own remarks and replies; whoever manages
users may delete any (not edit). Every edit keeps the earlier text. A deleted remark that has
replies stays as "Remark deleted" without its text and images; one without replies disappears.
Images are uploaded first (as drafts), then linked to the remark whose Markdown refers to them;
drafts nobody posted are removed after a day (RM-2).
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from momato.db.base import utcnow
from momato.db.ids import in_ids
from momato.db.models import Attachment, Post, PostRevision, Project
from momato.domain.access import Permission
from momato.domain.errors import (
    AuthenticationRequiredError,
    NotFoundError,
    PermissionDeniedError,
    RuleViolationError,
)
from momato.identity.principal import Principal
from momato.schemas.projects import PersonRef
from momato.schemas.remarks import (
    AttachmentOut,
    RemarkCreate,
    RemarkList,
    RemarkOut,
    RemarkUpdate,
    RemarkVersion,
)
from momato.services import common
from momato.services.attachments import AttachmentStore, attachment_out, store_image
from momato.services.markdown import attachment_ids_in, render_markdown
from momato.services.projects_access import ProjectAccess

DRAFT_LIFETIME = timedelta(days=1)


@dataclass(frozen=True)
class AttachmentFile:
    path: Path
    content_type: str
    filename: str


class RemarkService:
    def __init__(self, session: Session, principal: Principal, store: AttachmentStore) -> None:
        self.session = session
        self.principal = principal
        self.store = store
        self.access = ProjectAccess(session, principal)

    # ------------------------------------------------------------------ reading

    def for_project(self, number: int, limit: int | None = None) -> RemarkList:
        """Remarks newest first, each with its replies oldest first; `limit` keeps the newest."""
        project = self.access.visible(number)
        posts = list(
            self.session.scalars(
                select(Post).where(Post.project_id == project.id).order_by(Post.created_at, Post.id)
            )
        )
        context = _Context.load(self.session, self.principal, posts, self._can_comment(project))
        replies: dict[int, list[Post]] = defaultdict(list)
        for post in posts:
            if post.parent_id is not None:
                replies[post.parent_id].append(post)
        remarks = [p for p in posts if p.parent_id is None]
        remarks.reverse()  # newest first
        count = sum(1 for p in remarks if p.deleted_at is None)
        shown = remarks if limit is None else remarks[:limit]
        return RemarkList(
            items=[context.out(p, replies.get(p.id, [])) for p in shown],
            count=count,
            can_comment=context.can_comment,
        )

    def _can_comment(self, project: Project) -> bool:
        return self.access.can(project, Permission.PROJECT_COMMENT)

    def _one(self, post: Post, project: Project) -> RemarkOut:
        """A remark with its replies, or a reply on its own."""
        replies = list(
            self.session.scalars(
                select(Post).where(Post.parent_id == post.id).order_by(Post.created_at, Post.id)
            )
        )
        context = _Context.load(
            self.session, self.principal, [post, *replies], self._can_comment(project)
        )
        return context.out(post, replies)

    def _post(self, remark_id: int) -> tuple[Post, Project]:
        """A remark or reply of a project the caller can see (otherwise not found)."""
        post = self.session.get(Post, remark_id)
        project = self.session.get(Project, post.project_id) if post is not None else None
        if post is None or project is None:
            raise NotFoundError(f"no remark {remark_id}")
        self.access.visible(project.number)
        return post, project

    def history(self, remark_id: int) -> list[RemarkVersion]:
        """Every version of a remark, oldest first; the last one is the text as it is now."""
        post, _project = self._post(remark_id)
        if post.deleted_at is not None:
            raise NotFoundError(f"no remark {remark_id}")
        revisions = list(
            self.session.scalars(
                select(PostRevision)
                .where(PostRevision.post_id == post.id)
                .order_by(PostRevision.rev)
            )
        )
        last_writer = post.edited_by_id or post.author_id
        writers = common.person_refs(
            self.session, {r.written_by_id for r in revisions} | {last_writer}
        )
        via = common.token_names(
            self.session,
            [r.api_token_id for r in revisions] + [post.api_token_id, post.edited_api_token_id],
        )
        versions = [
            _version(
                r.rev,
                writers[r.written_by_id],
                r.written_at,
                r.body_md,
                via.get(r.api_token_id or 0),
            )
            for r in revisions
        ]
        last_via = post.edited_api_token_id if post.edited_by_id else post.api_token_id
        versions.append(
            _version(
                len(revisions) + 1,
                writers[last_writer],
                post.edited_at or post.created_at,
                post.body_md,
                via.get(last_via or 0),
            )
        )
        return versions

    # ------------------------------------------------------------------ writing

    def add(self, number: int, data: RemarkCreate) -> RemarkOut:
        project = self.access.commentable(number)
        post = Post(
            project_id=project.id,
            author_id=self.principal.user_id,
            api_token_id=self.principal.token_id,
            body_md=_body(data.body_md),
        )
        self.session.add(post)
        self.session.flush()
        self._claim_attachments(post)
        self.session.commit()
        return self._one(post, project)

    def reply(self, remark_id: int, data: RemarkCreate) -> RemarkOut:
        parent, project = self._post(remark_id)
        if parent.parent_id is not None:
            raise RuleViolationError("a reply goes to a remark, not to another reply")
        if parent.deleted_at is not None:
            raise RuleViolationError("this remark was deleted")
        self.access.commentable(project.number)
        body = _body(data.body_md)
        _no_images(body)
        reply = Post(
            project_id=project.id,
            parent_id=parent.id,
            author_id=self.principal.user_id,
            api_token_id=self.principal.token_id,
            body_md=body,
        )
        self.session.add(reply)
        self.session.commit()
        return self._one(reply, project)

    def update(self, remark_id: int, data: RemarkUpdate) -> RemarkOut:
        """Edit a remark or reply: its author, who must still be allowed to comment."""
        post, project = self._post(remark_id)
        if post.deleted_at is not None:
            raise NotFoundError(f"no remark {remark_id}")
        if not self._is_author(post):
            raise PermissionDeniedError("only the author can change this remark")
        self.access.commentable(project.number)
        body = _body(data.body_md)
        if post.parent_id is not None:
            _no_images(body)
        revisions = self.session.scalar(select(func.count()).where(PostRevision.post_id == post.id))
        self.session.add(
            PostRevision(
                post_id=post.id,
                rev=(revisions or 0) + 1,
                body_md=post.body_md,
                written_by_id=post.edited_by_id or post.author_id,
                written_at=post.edited_at or post.created_at,
                api_token_id=post.edited_api_token_id if post.edited_by_id else post.api_token_id,
            )
        )
        post.body_md = body
        post.edited_at = utcnow()
        post.edited_by_id = self.principal.user_id
        post.edited_api_token_id = self.principal.token_id
        self._claim_attachments(post)
        self.session.commit()
        return self._one(post, project)

    def delete(self, remark_id: int) -> None:
        post, _project = self._post(remark_id)
        if post.deleted_at is not None:
            raise NotFoundError(f"no remark {remark_id}")
        moderator = self.principal.can(Permission.USERS_MANAGE)
        if not (self._is_author(post) or moderator):
            raise PermissionDeniedError("you cannot delete this remark")
        files: list[str] = []
        has_replies = (
            self.session.scalar(select(func.count()).where(Post.parent_id == post.id)) or 0
        ) > 0
        if post.parent_id is None and has_replies:
            files += self._drop_images(post)
            self.session.execute(delete(PostRevision).where(PostRevision.post_id == post.id))
            post.body_md = ""
            post.deleted_at = utcnow()
        else:
            files += self._remove(post)
            parent = self.session.get(Post, post.parent_id) if post.parent_id else None
            if parent is not None and parent.deleted_at is not None:
                siblings = self.session.scalar(
                    select(func.count()).where(Post.parent_id == parent.id, Post.id != post.id)
                )
                if not siblings:  # the placeholder has nothing left to hold
                    files += self._remove(parent)
        self.session.commit()
        for public_id in files:  # only once the database no longer refers to them
            self.store.delete(public_id)

    def _is_author(self, post: Post) -> bool:
        return post.author_id == self.principal.user_id and not self.principal.is_anonymous

    def _drop_images(self, post: Post) -> list[str]:
        ids = list(
            self.session.scalars(select(Attachment.public_id).where(Attachment.post_id == post.id))
        )
        self.session.execute(delete(Attachment).where(Attachment.post_id == post.id))
        return ids

    def _remove(self, post: Post) -> list[str]:
        """Delete a post row with its history and images."""
        files = self._drop_images(post)
        self.session.execute(delete(PostRevision).where(PostRevision.post_id == post.id))
        self.session.delete(post)
        self.session.flush()
        return files

    def _claim_attachments(self, post: Post) -> None:
        """Link the uploader's draft images that this remark's Markdown refers to."""
        referenced = attachment_ids_in(post.body_md)
        if not referenced:
            return
        drafts = self.session.scalars(
            select(Attachment).where(
                Attachment.public_id.in_(referenced),
                Attachment.project_id == post.project_id,
                Attachment.post_id.is_(None),
                Attachment.uploader_id == self.principal.user_id,
            )
        )
        for attachment in drafts:
            attachment.post_id = post.id

    # ------------------------------------------------------------------ files

    def upload(self, number: int, filename: str | None, data: bytes) -> AttachmentOut:
        project = self.access.commentable(number)
        attachment = store_image(
            self.store, filename, data, project_id=project.id, uploader_id=self.principal.user_id
        )
        stale = self._remove_stale_drafts()
        self.session.add(attachment)
        self.session.commit()
        for public_id in stale:
            self.store.delete(public_id)
        return attachment_out(attachment)

    def open_attachment(self, public_id: str) -> AttachmentFile:
        """The file behind an attachment, if the caller can see its project."""
        attachment = self.session.scalars(
            select(Attachment).where(Attachment.public_id == public_id)
        ).one_or_none()
        project = (
            self.session.get(Project, attachment.project_id) if attachment is not None else None
        )
        if attachment is None or project is None:
            raise NotFoundError("no such attachment")
        self.access.visible(project.number)  # raises unless visible
        path = self.store.path(attachment.public_id)
        if not path.exists():
            raise NotFoundError("the file is missing")
        return AttachmentFile(
            path=path, content_type=attachment.content_type, filename=attachment.filename
        )

    def _remove_stale_drafts(self) -> list[str]:
        """Delete draft rows nobody posted within a day; returns their ids (files go later)."""
        cutoff = utcnow() - DRAFT_LIFETIME
        stale = self.session.execute(
            select(Attachment.id, Attachment.public_id).where(
                Attachment.post_id.is_(None), Attachment.created_at < cutoff
            )
        ).all()
        if stale:
            self.session.execute(
                delete(Attachment).where(in_ids(Attachment.id, [i for i, _ in stale]))
            )
        return [public_id for _, public_id in stale]

    def preview(self, body: str) -> str:
        """Markdown rendered as a remark would be (the composer's Preview). It exposes nothing,
        so any signed-in person may use it, whatever their rights."""
        if self.principal.is_anonymous:
            raise AuthenticationRequiredError("log in to write remarks")
        return render_markdown(body)


# ---------------------------------------------------------------- helpers


def _body(text: str) -> str:
    body = text.strip()
    if not body:
        raise RuleViolationError("a remark needs some text or an image")
    return body


def _no_images(body: str) -> None:
    if attachment_ids_in(body):
        raise RuleViolationError("replies are text only: attach images to a remark")


def _version(
    rev: int, writer: PersonRef, at: datetime, body: str, via: str | None = None
) -> RemarkVersion:
    return RemarkVersion(
        rev=rev,
        written_by=writer,
        written_at=at,
        via=via,
        body_md=body,
        html=render_markdown(body),
    )


@dataclass(frozen=True)
class _Context:
    """What turning posts into output needs, loaded once for a whole conversation."""

    principal: Principal
    can_comment: bool
    moderator: bool
    authors: dict[int, PersonRef]
    versions: dict[int, int]
    tokens: dict[int, str]

    @classmethod
    def load(
        cls, session: Session, principal: Principal, posts: Sequence[Post], can_comment: bool
    ) -> _Context:
        ids = [p.id for p in posts]
        counts: dict[int, int] = {}
        if ids:
            rows = session.execute(
                select(PostRevision.post_id, func.count())
                .where(in_ids(PostRevision.post_id, ids))
                .group_by(PostRevision.post_id)
            ).all()
            counts = {post_id: int(n) for post_id, n in rows}
        return cls(
            principal=principal,
            can_comment=can_comment,
            moderator=principal.can(Permission.USERS_MANAGE),
            authors=common.person_refs(session, {p.author_id for p in posts}),
            versions=counts,
            tokens=common.token_names(
                session, [i for p in posts for i in (p.api_token_id, p.edited_api_token_id)]
            ),
        )

    def out(self, post: Post, replies: Sequence[Post] = ()) -> RemarkOut:
        deleted = post.deleted_at is not None
        own = post.author_id == self.principal.user_id and not self.principal.is_anonymous
        return RemarkOut(
            id=post.id,
            parent_id=post.parent_id,
            author=None if deleted else self.authors.get(post.author_id),
            created_at=post.created_at,
            edited_at=post.edited_at,
            via=None if deleted else self.tokens.get(post.api_token_id or 0),
            edited_via=None if deleted else self.tokens.get(post.edited_api_token_id or 0),
            versions=self.versions.get(post.id, 0) + 1,
            deleted=deleted,
            body_md="" if deleted else post.body_md,
            html="" if deleted else render_markdown(post.body_md),
            can_edit=own and self.can_comment and not deleted,
            can_delete=(own or self.moderator) and not deleted,
            replies=[self.out(r) for r in replies],
        )
