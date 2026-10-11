"""Uploaded images: type sniffing, size limits, atomic writes, deletion, and their rows and links.

Files live in <data_dir>/uploads/<public_id> (no extension; the content type is in the database).
Only raster images are accepted, recognised by their first bytes rather than by the name or the
browser's claim: SVG (which can carry scripts) is refused (RM-2).
"""

import secrets
from pathlib import Path
from urllib.parse import quote

from momato.db.models import Attachment
from momato.domain.errors import RuleViolationError
from momato.schemas.remarks import AttachmentOut
from momato.services.markdown import ATTACHMENT_URL_PREFIX

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
]

_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def sniff_image_type(data: bytes) -> str | None:
    """The image's content type from its first bytes, or None if it is not an accepted image."""
    for signature, content_type in _SIGNATURES:
        if data.startswith(signature):
            return content_type
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def new_public_id() -> str:
    return secrets.token_hex(16)


def safe_filename(name: str | None, content_type: str) -> str:
    """A display/download name without paths or odd characters, with a fitting extension."""
    base = Path(name or "image").name.strip() or "image"
    base = "".join(c if c.isalnum() or c in "._- " else "_" for c in base)[:120]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    return f"{stem or 'image'}{_EXTENSIONS[content_type]}"


class AttachmentStore:
    """The uploads folder."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def path(self, public_id: str) -> Path:
        if not public_id.isalnum():
            raise ValueError("invalid attachment id")
        return self.directory / public_id

    def save(self, public_id: str, data: bytes) -> None:
        """Write atomically: a crash never leaves a half-written file under the final name."""
        self.directory.mkdir(parents=True, exist_ok=True)
        final = self.path(public_id)
        temporary = final.with_name(f"{public_id}.part")
        temporary.write_bytes(data)
        temporary.replace(final)

    def delete(self, public_id: str) -> None:
        self.path(public_id).unlink(missing_ok=True)


def attachment_url(public_id: str, filename: str) -> str:
    """Percent-encoded, so names with spaces still form a valid Markdown link."""
    return f"{ATTACHMENT_URL_PREFIX}{public_id}/{quote(filename)}"


def store_image(
    store: AttachmentStore, filename: str | None, data: bytes, *, project_id: int, uploader_id: int
) -> Attachment:
    """Check an uploaded image, save its file, and return its (not yet added) draft row."""
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise RuleViolationError(f"images can be at most {MAX_ATTACHMENT_BYTES // 1_000_000} MB")
    content_type = sniff_image_type(data)
    if content_type is None:
        raise RuleViolationError("only PNG, JPEG, GIF or WebP images can be attached")
    attachment = Attachment(
        project_id=project_id,
        uploader_id=uploader_id,
        public_id=new_public_id(),
        filename=safe_filename(filename, content_type),
        content_type=content_type,
        size=len(data),
    )
    store.save(attachment.public_id, data)
    return attachment


def attachment_out(attachment: Attachment) -> AttachmentOut:
    url = attachment_url(attachment.public_id, attachment.filename)
    return AttachmentOut(
        id=attachment.public_id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size=attachment.size,
        url=url,
        markdown=f"![{attachment.filename}]({url})",
    )
