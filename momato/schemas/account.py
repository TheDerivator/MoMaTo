"""The profile page document: one's own data and availability, read only (ADM-8)."""

from pydantic import BaseModel

from momato.schemas.admin import AvailabilityOut


class AccountOut(BaseModel):
    id: int
    name: str
    job_title: str | None
    org_path: list[str]  # from just below the root down to the person's node
    department: str | None  # the nearest flagged node (D-006)
    hue: int
    username: str | None
    email: str | None
    work_minutes: list[int]
    availability: list[AvailabilityOut]
    password_sign_in: bool  # whether there is a local password to change
    must_change_password: bool
