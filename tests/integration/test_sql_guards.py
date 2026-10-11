"""The test support that guards scale and MS SQL portability: statement counter, parameter cap."""

import pytest
from sqlalchemy import TextClause, bindparam, create_engine, text

from tests.conftest import MSSQL_MAX_PARAMETERS
from tests.helpers import count_statements


def test_the_counter_counts_statements_of_any_engine() -> None:
    engine = create_engine("sqlite://")
    with count_statements() as counter, engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        connection.execute(text("SELECT 2"))
        connection.execute(text("CREATE TABLE t (a INTEGER)"))
    assert counter.count == 3
    assert counter.selects == 2
    assert counter.statements[0] == "SELECT 1"
    engine.dispose()


def test_the_counter_stops_counting_when_the_block_ends() -> None:
    engine = create_engine("sqlite://")
    with count_statements() as counter, engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    with engine.connect() as connection:
        connection.execute(text("SELECT 2"))
    assert counter.count == 1
    engine.dispose()


def test_counters_are_independent() -> None:
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        with count_statements() as outer:
            connection.execute(text("SELECT 1"))
            with count_statements() as inner:
                connection.execute(text("SELECT 2"))
        assert (outer.count, inner.count) == (2, 1)
    engine.dispose()


def _in_list(count: int) -> tuple[TextClause, dict[str, list[int]]]:
    statement = text("SELECT COUNT(*) FROM (SELECT 1 AS x) WHERE x IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    return statement, {"ids": list(range(count))}


def test_a_statement_at_the_ms_sql_limit_passes() -> None:
    engine = create_engine("sqlite://")
    statement, params = _in_list(MSSQL_MAX_PARAMETERS)
    with engine.connect() as connection:
        assert connection.execute(statement, params).scalar_one() == 1
    engine.dispose()


def test_a_statement_over_the_ms_sql_limit_fails_the_test() -> None:
    """Id lists must be written into the SQL as integers instead (db/ids.py, M1)."""
    engine = create_engine("sqlite://")
    statement, params = _in_list(MSSQL_MAX_PARAMETERS + 1)
    with engine.connect() as connection, pytest.raises(AssertionError, match="2100"):
        connection.execute(statement, params)
    engine.dispose()


def test_bulk_inserts_are_exempt_from_the_parameter_cap() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE t (a INTEGER, b INTEGER)"))
        connection.execute(
            text("INSERT INTO t (a, b) VALUES (:a, :b)"),
            [{"a": n, "b": n} for n in range(1500)],  # 3,000 parameters in one executemany
        )
        assert connection.execute(text("SELECT COUNT(*) FROM t")).scalar_one() == 1500
    engine.dispose()
