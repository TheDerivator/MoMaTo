"""Booking steps and week states, from the shared hand-derived tables, plus properties."""

from collections.abc import Mapping
from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from momato.domain import timesheet as ts
from tests.helpers import load_fixture

BOOKING = load_fixture("booking")["cases"]
WEEKS = load_fixture("week_states")["cases"]


def _cells(raw: Mapping[str, int]) -> dict[ts.Cell, int]:
    return {(key.split(":")[0], key.split(":")[1]): minutes for key, minutes in raw.items()}


def _key(cell: ts.Cell | None) -> str | None:
    return None if cell is None else f"{cell[0]}:{cell[1]}"


@pytest.mark.parametrize("case", BOOKING, ids=lambda c: c["name"])
def test_booking_follows_the_hand_derived_table(case: dict[str, object]) -> None:
    """[R4.8]"""
    day = _cells(case["day"])  # pyright: ignore[reportArgumentType]
    step = int(case.get("step", 60))  # pyright: ignore[reportArgumentType]
    line, task = str(case["line"]), str(case["task"])
    if case["op"] == "add":
        cap = int(case.get("cap", 600))  # pyright: ignore[reportArgumentType]
        result = ts.add_step(day, line, task, step=step, cap=cap)
    else:
        picker = list(case["picker"])  # pyright: ignore[reportArgumentType]
        result = ts.remove_step(day, line, task, step=step, picker_order=picker)
    assert dict(result.day) == _cells(case["expect_day"])  # pyright: ignore[reportArgumentType]
    assert _key(result.cell) == case["changed"]


def test_a_booking_never_changes_the_day_it_was_given() -> None:
    day = {("p1", "t1"): 60}
    ts.add_step(day, "p1", "t1", step=60, cap=600)
    ts.remove_step(day, "p1", "t1", step=60, picker_order=["t1"])
    assert day == {("p1", "t1"): 60}


LINES = ["p1", "p2", "other", "timeoff"]
TASKS = ["t1", "t2", "general"]
operations = st.lists(
    st.tuples(st.sampled_from(["add", "remove"]), st.sampled_from(LINES), st.sampled_from(TASKS)),
    max_size=60,
)


@given(operations, st.sampled_from([15, 30, 60]), st.sampled_from([480, 600, 720]))
def test_after_any_sequence_no_value_is_negative_and_no_day_exceeds_the_cap(
    steps: list[tuple[str, str, str]], step: int, cap: int
) -> None:
    """[R4.8]"""
    day: Mapping[ts.Cell, int] = {}
    for op, line, task in steps:
        if op == "add":
            day = ts.add_step(day, line, task, step=step, cap=cap).day
        else:
            day = ts.remove_step(day, line, task, step=step, picker_order=TASKS).day
        assert all(value >= 0 for value in day.values())
        assert sum(day.values()) <= cap


@given(operations, st.sampled_from(LINES), st.sampled_from(TASKS))
def test_an_accepted_plus_followed_by_minus_restores_the_day(
    steps: list[tuple[str, str, str]], line: str, task: str
) -> None:
    """[R4.8]"""
    day: Mapping[ts.Cell, int] = {}
    for op, ln, tk in steps:
        if op == "add":
            day = ts.add_step(day, ln, tk, step=60, cap=600).day
        else:
            day = ts.remove_step(day, ln, tk, step=60, picker_order=TASKS).day
    added = ts.add_step(day, line, task, step=60, cap=600)
    if added.cell is None:
        assert added.day == day
        return
    undone = ts.remove_step(added.day, line, task, step=60, picker_order=TASKS)
    assert {k: v for k, v in undone.day.items() if v} == {k: v for k, v in day.items() if v}


# ---------------------------------------------------------------- week states


@pytest.mark.parametrize("case", WEEKS, ids=lambda c: c["name"])
def test_week_states_follow_the_hand_derived_table(case: dict[str, object]) -> None:
    """[R4.9]"""
    view = ts.week_view(
        case["targets"],  # pyright: ignore[reportArgumentType]
        case["booked"],  # pyright: ignore[reportArgumentType]
        today_index=int(case["today_index"]),  # pyright: ignore[reportArgumentType]
        submitted=bool(case["submitted"]),
        week_number=int(case["week_number"]),  # pyright: ignore[reportArgumentType]
    )
    assert view.state == case["state"]
    assert view.full_days == case["full_days"]
    assert list(view.open_days) == case["open_days"]
    assert view.title == case["title"]
    assert view.cta == case["cta"]
    assert view.headline == case["headline"]
    assert view.subline == case["subline"]
    assert [d.tag.value for d in view.days] == case["tags"]


def test_a_day_view_has_its_fill_fraction() -> None:
    """[R4.9]"""
    views = ts.day_views([480, 480, 480, 480, 0], [240, 600, 0, 120, 0], today_index=2)
    assert [v.fill for v in views] == [Fraction(1, 2), Fraction(1), Fraction(0), Fraction(1, 4), 0]
    assert [v.working for v in views] == [True, True, True, True, False]


def test_a_week_has_five_days() -> None:
    with pytest.raises(ValueError, match="five working days"):
        ts.week_view([480] * 4, [0] * 4, today_index=0, submitted=False, week_number=1)


def test_a_person_without_working_days_has_a_fresh_week() -> None:
    view = ts.week_view([0] * 5, [0] * 5, today_index=2, submitted=False, week_number=1)
    assert view.state is ts.WeekState.FRESH
    assert view.working_days == 0
    assert view.subline == "0 of 0 h logged."  # nothing to be "next up"


def test_one_working_day_is_spelled_in_the_singular() -> None:
    view = ts.week_view(
        [0, 0, 480, 0, 0], [0, 0, 480, 0, 0], today_index=7, submitted=False, week_number=1
    )
    assert view.subline == "All one day is in. One tap to submit."


@given(
    st.lists(st.sampled_from([0, 240, 480, 600]), min_size=5, max_size=5),
    st.lists(st.integers(0, 700), min_size=5, max_size=5),
    st.integers(0, 7),
    st.booleans(),
)
def test_exactly_one_state_applies_and_it_is_the_first_row_of_the_table(
    targets: list[int], booked: list[int], today_index: int, submitted: bool
) -> None:
    """[R4.9] An independent reading of the table, written out day by day."""
    view = ts.week_view(
        targets, booked, today_index=today_index, submitted=submitted, week_number=7
    )
    working = [i for i in range(5) if targets[i] > 0]
    full = [i for i in working if booked[i] >= targets[i]]
    open_ = [i for i in working if i not in full and i < today_index - 1]
    if submitted:
        expected = ts.WeekState.SUBMITTED
    elif open_:
        expected = ts.WeekState.OPEN
    elif working and len(full) == len(working):
        expected = ts.WeekState.FULL
    elif full:
        expected = ts.WeekState.PARTIAL
    else:
        expected = ts.WeekState.FRESH
    assert view.state is expected
    assert list(view.open_days) == open_
    assert view.full_days == len(full)
    assert view.total_minutes == sum(booked)
    assert view.target_minutes == sum(targets)
