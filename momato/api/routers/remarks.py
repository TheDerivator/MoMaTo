"""Remark endpoints: a project's remarks and replies, editing with history, images, preview."""

from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile, status
from fastapi.responses import FileResponse

from momato.api.deps import Remarks
from momato.schemas.remarks import (
    AttachmentOut,
    MarkdownPreviewIn,
    MarkdownPreviewOut,
    RemarkCreate,
    RemarkList,
    RemarkOut,
    RemarkUpdate,
    RemarkVersion,
)
from momato.services.attachments import MAX_ATTACHMENT_BYTES

router = APIRouter(tags=["remarks"])


@router.get("/projects/{number}/remarks")
def list_remarks(
    number: int,
    service: Remarks,
    limit: Annotated[int | None, Query(ge=1, le=200, description="keep the newest n")] = None,
) -> RemarkList:
    """Remarks newest first, each with its replies oldest first."""
    return service.for_project(number, limit)


@router.post("/projects/{number}/remarks", status_code=status.HTTP_201_CREATED)
def add_remark(number: int, body: RemarkCreate, service: Remarks) -> RemarkOut:
    """Markdown body; images referenced from uploads of yours are attached to the remark."""
    return service.add(number, body)


@router.post("/remarks/{remark_id}/replies", status_code=status.HTTP_201_CREATED)
def add_reply(remark_id: int, body: RemarkCreate, service: Remarks) -> RemarkOut:
    return service.reply(remark_id, body)


@router.patch("/remarks/{remark_id}")
def update_remark(remark_id: int, body: RemarkUpdate, service: Remarks) -> RemarkOut:
    return service.update(remark_id, body)


@router.delete("/remarks/{remark_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_remark(remark_id: int, service: Remarks) -> None:
    service.delete(remark_id)


@router.get("/remarks/{remark_id}/history")
def remark_history(remark_id: int, service: Remarks) -> list[RemarkVersion]:
    """Every version of an edited remark, oldest first; the last is the text as it is now."""
    return service.history(remark_id)


@router.post("/projects/{number}/attachments", status_code=status.HTTP_201_CREATED)
def upload_attachment(
    number: int, file: Annotated[UploadFile, File()], service: Remarks
) -> AttachmentOut:
    """Upload an image (PNG, JPEG, GIF, WebP; at most 10 MB) to use in a remark."""
    data = file.file.read(MAX_ATTACHMENT_BYTES + 1)
    return service.upload(number, file.filename, data)


@router.get("/attachments/{public_id}/{filename}", response_class=FileResponse)
def download_attachment(public_id: str, filename: str, service: Remarks) -> FileResponse:
    """The image, for anyone who can see its project. `filename` is only cosmetic."""
    del filename
    found = service.open_attachment(public_id)
    return FileResponse(
        found.path,
        media_type=found.content_type,
        filename=found.filename,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/markdown/preview")
def preview(body: MarkdownPreviewIn, service: Remarks) -> MarkdownPreviewOut:
    """Render Markdown exactly as a remark would be shown."""
    return MarkdownPreviewOut(html=service.preview(body.body_md))
