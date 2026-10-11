"""The schema as MS SQL would get it, compiled offline (no server needed): Unicode text, integer
minutes, `Numeric` days, `DATETIME2`, filtered unique indexes that keep their WHERE, and no
cascading deletes (MS SQL refuses multiple cascade paths and self-references)."""

import pytest
from sqlalchemy import Boolean, Date, Enum, Float, Index, Integer, Numeric, String, Table
from sqlalchemy.dialects import mssql
from sqlalchemy.schema import CreateIndex, CreateTable

import momato.db.models  # noqa: F401  (registers every table)
from momato.db.base import Base

DIALECT = mssql.dialect()
# Offline, the dialect assumes a pre-2008 server (DATE would become DATETIME); say what we target.
DIALECT.server_version_info = (16, 0, 1000)  # SQL Server 2022
TABLES = sorted(Base.metadata.tables.values(), key=lambda t: t.name)


@pytest.mark.parametrize("table", TABLES, ids=[t.name for t in TABLES])
def test_a_table_as_ms_sql_creates_it(table: Table) -> None:
    ddl = str(CreateTable(table).compile(dialect=DIALECT))
    assert "CASCADE" not in ddl.upper()
    for column in table.columns:
        assert not isinstance(column.type, Float), f"{table.name}.{column.name} is a float"
        if isinstance(column.type, String) and not isinstance(column.type, Enum):
            rendered = column.type.compile(dialect=DIALECT)
            assert rendered.startswith("NVARCHAR"), f"{table.name}.{column.name} is {rendered}"


def _rendered(table: str, column: str) -> str:
    return Base.metadata.tables[table].c[column].type.compile(dialect=DIALECT)


def test_time_is_integer_minutes() -> None:
    assert isinstance(Base.metadata.tables["time_entries"].c.minutes.type, Integer)
    for column in (
        "work_minutes_mon",
        "work_minutes_tue",
        "work_minutes_wed",
        "work_minutes_thu",
        "work_minutes_fri",
    ):
        assert isinstance(Base.metadata.tables["users"].c[column].type, Integer)


def test_days_are_numeric_never_float() -> None:
    for table, column in [("planned_days", "days"), ("availability", "days")]:
        assert isinstance(Base.metadata.tables[table].c[column].type, Numeric)
        assert _rendered(table, column) == "NUMERIC(6, 2)"


def test_timestamps_are_datetime2_and_dates_are_dates() -> None:
    assert _rendered("projects", "created_at") == "DATETIME2"
    assert _rendered("time_entries", "updated_at") == "DATETIME2"
    assert isinstance(Base.metadata.tables["projects"].c.start_date.type, Date)
    assert _rendered("projects", "start_date") == "DATE"
    assert isinstance(Base.metadata.tables["tasks"].c.is_milestone.type, Boolean)


def test_long_text_is_nvarchar_max() -> None:
    assert _rendered("posts", "body_md") == "NVARCHAR(max)"
    assert _rendered("projects", "goal") == "NVARCHAR(max)"
    assert _rendered("project_details", "value") == "NVARCHAR(max)"


FILTERED = [
    (table, index)
    for table in TABLES
    for index in table.indexes
    if isinstance(index, Index) and index.dialect_options["sqlite"].get("where") is not None
]


def test_the_schema_has_its_filtered_unique_indexes() -> None:
    names = {index.name for _, index in FILTERED}
    assert names == {
        "uq_time_entries_task_cell",
        "uq_time_entries_general_cell",
        "uq_time_entries_category_cell",
        "uq_users_username",  # nullable and unique: MS SQL's UNIQUE would allow one NULL only
        "uq_users_email",
    }
    assert all(index.unique for _, index in FILTERED)


@pytest.mark.parametrize(("table", "index"), FILTERED, ids=[i.name or "" for _, i in FILTERED])
def test_filtered_indexes_stay_filtered(table: Table, index: Index) -> None:
    ddl = str(CreateIndex(index).compile(dialect=DIALECT))
    assert " WHERE " in ddl, f"{index.name} on {table.name} needs `mssql_where` too"


def test_no_foreign_key_cascades() -> None:
    for table in TABLES:
        for constraint in table.foreign_key_constraints:
            assert constraint.ondelete is None, f"{table.name}.{constraint.name}"
            assert constraint.onupdate is None, f"{table.name}.{constraint.name}"


def test_every_constraint_has_a_deterministic_name() -> None:
    for table in TABLES:
        for constraint in table.constraints:
            assert constraint.name, f"an unnamed constraint on {table.name}"
