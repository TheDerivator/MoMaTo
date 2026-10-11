"""Meta endpoints: health."""

from fastapi import APIRouter

from momato import __version__
from momato.schemas.meta import Health

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> Health:
    """Liveness probe: answers without touching the database."""
    return Health(status="ok", version=__version__)
