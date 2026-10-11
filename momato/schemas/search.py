"""Shapes of the server-side pickers: projects and people (SH-12, TS-8, PD-4, AP-7)."""

from pydantic import BaseModel

from momato.domain.projects import ProjectStatus


class ProjectHit(BaseModel):
    number: int
    name: str
    status: ProjectStatus
    org_node_name: str


class PersonHit(BaseModel):
    id: int
    name: str
    job_title: str | None
    org_node_id: int | None
    hue: int
