"""Fixtures for API tests on the sample data: clients signed in as sample people."""

from collections.abc import Callable, Iterator
from contextlib import ExitStack

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from momato.config import Settings
from momato.db.models import Project, Role, RoleAssignment, User
from momato.db.session import Database
from momato.domain.access import Scope
from momato.web import create_app
from momato.web.csrf import CSRF_COOKIE, CSRF_HEADER
from tests.conftest import DEMO_PASSWORD, TEST_ADMIN_PASSWORD
from tests.helpers import login

type ClientFactory = Callable[..., TestClient]


@pytest.fixture
def app(sample_settings: Settings) -> Iterator[FastAPI]:
    """The application on a fresh copy of the sample database (lifespan started once)."""
    application = create_app(sample_settings)
    with TestClient(application):
        yield application


@pytest.fixture
def clients(app: FastAPI) -> ClientFactory:
    """`clients("anna.claes")` is a frontend-like client signed in as that person; `clients()`
    is a visitor; `clients("admin", TEST_ADMIN_PASSWORD)` the administrator. Own cookie jars."""

    def make(username: str | None = None, password: str = DEMO_PASSWORD) -> TestClient:
        client = TestClient(app)
        client.get("/api/health")  # receive the CSRF cookie
        client.headers[CSRF_HEADER] = client.cookies[CSRF_COOKIE]
        if username is not None:
            response = login(client, username, password)
            assert response.status_code == 200, response.text
        return client

    return make


@pytest.fixture
def admin(clients: ClientFactory) -> TestClient:
    return clients("admin", TEST_ADMIN_PASSWORD)


@pytest.fixture
def anna(clients: ClientFactory) -> TestClient:
    """Anna Claes, STL › Quality: a plain signed-in person (the defaults only)."""
    return clients("anna.claes")


@pytest.fixture
def stack() -> Iterator[ExitStack]:
    with ExitStack() as exit_stack:
        yield exit_stack


def grant(database: Database, username: str, role_key: str, scope: Scope) -> None:
    """Give a sample person a role at a scope (a test setup shortcut, not the access service)."""
    with database.session(write=True) as session:
        user = session.scalar(select(User).where(User.username == username))
        role = session.scalar(select(Role).where(Role.key == role_key))
        assert user is not None
        assert role is not None
        assignment = RoleAssignment(user_id=user.id, role_id=role.id)
        assignment.scope = scope
        session.add(assignment)


def project_node(database: Database, number: int) -> int:
    with database.session() as session:
        node = session.scalar(select(Project.org_node_id).where(Project.number == number))
        assert node is not None
        return node
