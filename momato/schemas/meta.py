"""Shapes of the meta endpoints (health)."""

from typing import Literal

from pydantic import BaseModel


class Health(BaseModel):
    status: Literal["ok"]
    version: str
