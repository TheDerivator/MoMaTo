"""Case-insensitive text matching that works for all of Unicode on every backend.

SQLite's built-in `lower()` only folds ASCII ("É" stays "É"), so on SQLite `casefold(x)` compiles to
a Python function registered on each connection (see db/session.py); elsewhere to `LOWER(x)`.
"""

from typing import Any

from sqlalchemy import ColumnElement, SQLColumnExpression, Unicode
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.functions import FunctionElement

SQLITE_CASEFOLD_FUNCTION = "mm_casefold"


class casefold(FunctionElement[str]):  # noqa: N801  (SQL function style)
    type = Unicode()
    inherit_cache = True


@compiles(casefold)
def _casefold_default(element: casefold, compiler: SQLCompiler, **kw: Any) -> str:
    return f"LOWER({compiler.process(element.clauses, **kw)})"


@compiles(casefold, "sqlite")
def _casefold_sqlite(element: casefold, compiler: SQLCompiler, **kw: Any) -> str:
    return f"{SQLITE_CASEFOLD_FUNCTION}({compiler.process(element.clauses, **kw)})"


def sqlite_casefold(value: str | None) -> str | None:
    return value.casefold() if value is not None else None


def contains_ci(column: SQLColumnExpression[str], needle: str) -> ColumnElement[bool]:
    """`column` contains `needle`, ignoring case; `%` and `_` in the needle are literal."""
    return casefold(column).contains(needle.casefold(), autoescape=True)
