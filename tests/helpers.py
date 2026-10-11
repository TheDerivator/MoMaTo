"""Test helpers: the SQL statement counter that proves queries don't grow, shared fixture tables."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import Engine, event
from sqlalchemy.engine.interfaces import DBAPICursor, ExecutionContext

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from httpx2 import Response


@dataclass
class StatementCounter:
    """The SQL statements sent to any engine while `count_statements` was active."""

    statements: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.statements)

    @property
    def selects(self) -> int:
        return sum(1 for s in self.statements if s.lstrip()[:6].upper() == "SELECT")


@contextmanager
def count_statements() -> Iterator[StatementCounter]:
    """Count SQL statements across every engine and thread (the app runs in the client's thread).

    The scale principle (PLAN.md, test strategy 8): the number of statements of a request must not
    grow with the number of rows, so tests compare the count on a small and a large data set.
    """
    counter = StatementCounter()

    def record(
        conn: object,
        cursor: DBAPICursor,
        statement: str,
        parameters: object,
        context: ExecutionContext | None,
        executemany: bool,
    ) -> None:
        counter.statements.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    try:
        yield counter
    finally:
        event.remove(Engine, "before_cursor_execute", record)


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> Any:
    """A shared fixture table (tests/fixtures/<name>.json): one table, tested in Python and JS."""
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def login(client: TestClient, username: str, password: str) -> Response:
    """Sign in through the API; the session cookie stays in the client."""
    return client.post("/api/auth/login", json={"username": username, "password": password})
