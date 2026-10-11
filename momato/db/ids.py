"""`column IN (ids)` for any number of ids on every backend: the ids are written into the SQL as
integer literals instead of being sent as parameters, because MS SQL takes at most 2,100
parameters in one statement. Integers only, so nothing is injected."""

from collections.abc import Iterable

from sqlalchemy import ColumnElement, Integer, bindparam
from sqlalchemy.orm import InstrumentedAttribute


def in_ids(
    column: InstrumentedAttribute[int] | InstrumentedAttribute[int | None], ids: Iterable[int]
) -> ColumnElement[bool]:
    values = sorted({int(i) for i in ids})
    return column.in_(bindparam(None, values, type_=Integer, expanding=True, literal_execute=True))
