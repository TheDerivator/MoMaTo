"""ASGI entrypoint (`uvicorn app:app`). The application itself lives in the `momato` package."""

from momato.web import create_app

app = create_app()
