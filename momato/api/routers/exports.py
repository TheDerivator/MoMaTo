"""Export endpoints (EXP-1 – EXP-4): the project list and booked time as CSV or XLSX files."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from momato.api.deps import Exports
from momato.api.routers.projects import Filters
from momato.services.export_files import ExportFormat, chunks
from momato.services.exports import Download

router = APIRouter(prefix="/exports", tags=["exports"])

Format = Annotated[ExportFormat, Query(alias="format", description="csv or xlsx")]


def _file(download: Download) -> StreamingResponse:
    return StreamingResponse(
        chunks(download.file),
        media_type=download.media_type,
        headers={"Content-Disposition": f'attachment; filename="{download.filename}"'},
    )


@router.get("/projects")
def export_projects(
    exports: Exports, filters: Filters, kind: Format = ExportFormat.CSV
) -> StreamingResponse:
    """The project list as shown (the same filters as `GET /api/projects`): core fields and every
    detail field of the profile."""
    return _file(exports.projects(filters, kind))


@router.get("/time-entries")
def export_time_entries(
    exports: Exports,
    start: Annotated[date, Query(description="first day, ISO date")],
    end: Annotated[date, Query(description="last day, ISO date")],
    node: Annotated[int | None, Query(description="an org node: its whole branch")] = None,
    kind: Format = ExportFormat.CSV,
) -> StreamingResponse:
    """Booked time of a period (at most three years) for the people of a branch whose hours
    the caller may see: date, ISO week, person, organisation, project, task, category, hours,
    whether the week was submitted."""
    return _file(exports.time_entries(start, end, node, kind))
