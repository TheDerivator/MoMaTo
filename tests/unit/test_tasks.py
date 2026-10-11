"""Task status, slippage, timeline text, task dates and the standard phases."""

from datetime import date
from fractions import Fraction

import pytest

from momato.domain import tasks as t
from tests.helpers import load_fixture

TABLE = load_fixture("task_status")


def _iso(value: str) -> date:
    return date.fromisoformat(value)


@pytest.mark.parametrize(
    "case", TABLE["status"], ids=lambda c: f"{c['progress']}-{c['planned_start']}"
)
def test_task_status(case: dict[str, object]) -> None:
    """[R4.6]"""
    result = t.task_status(
        int(str(case["progress"])), _iso(str(case["planned_start"])), _iso(str(case["today"]))
    )
    assert result == case["status"]


@pytest.mark.parametrize("case", TABLE["slipped"], ids=lambda c: str(c["revised_end"]))
def test_slipped_and_effective_end(case: dict[str, str | bool | None]) -> None:
    """[R4.6]"""
    planned_end = _iso(str(case["planned_end"]))
    revised = _iso(str(case["revised_end"])) if case["revised_end"] else None
    assert t.is_slipped(planned_end, revised) is case["slipped"]
    assert t.effective_end(planned_end, revised) == _iso(str(case["effective_end"]))


@pytest.mark.parametrize("case", TABLE["status_text"], ids=lambda c: str(c["text"]))
def test_status_text_of_where_we_are(case: dict[str, str | int]) -> None:
    """[R4.6]"""
    assert t.status_text(t.TaskStatus(str(case["status"])), int(case["progress"])) == case["text"]


@pytest.mark.parametrize("case", TABLE["timeline"], ids=lambda c: f"{c['today']}-{c['text']}")
def test_timeline_text(case: dict[str, str]) -> None:
    """[R4.6]"""
    result = t.timeline_text(_iso(case["start"]), _iso(case["end"]), _iso(case["today"]))
    assert result == case["text"]


def test_task_dates_are_validated() -> None:
    t.validate_task_dates(date(2026, 1, 1), date(2026, 1, 1), None)  # a one-day task is fine
    t.validate_task_dates(date(2026, 1, 1), date(2026, 3, 1), date(2026, 3, 2))
    with pytest.raises(ValueError, match="before its start"):
        t.validate_task_dates(date(2026, 3, 1), date(2026, 2, 28), None)
    with pytest.raises(ValueError, match="after the planned end"):
        t.validate_task_dates(date(2026, 1, 1), date(2026, 3, 1), date(2026, 3, 1))
    with pytest.raises(ValueError, match="after the planned end"):
        t.validate_task_dates(date(2026, 1, 1), date(2026, 3, 1), date(2026, 2, 1))


DESIGN_PHASES = [
    t.TemplateTask("Study & scoping", Fraction("0"), Fraction("0.14")),
    t.TemplateTask("Supplier offers", Fraction("0.1"), Fraction("0.24")),
    t.TemplateTask("Order & delivery", Fraction("0.24"), Fraction("0.46"), True),
    t.TemplateTask("Installation", Fraction("0.44"), Fraction("0.72")),
    t.TemplateTask("Commissioning", Fraction("0.7"), Fraction("0.86"), True),
    t.TemplateTask("Handover & close-out", Fraction("0.86"), Fraction("1")),
]


def test_the_template_spreads_phases_over_the_project_span() -> None:
    """A 100-day project makes the template's fractions read as day offsets."""
    start = date(2026, 1, 1)
    end = date(2026, 4, 11)  # 100 days later
    planned = t.tasks_from_template(DESIGN_PHASES, start, end)
    spans = [(p.planned_start, p.planned_end) for p in planned]
    assert spans[0] == (date(2026, 1, 1), date(2026, 1, 15))
    assert spans[2] == (date(2026, 1, 25), date(2026, 2, 16))
    assert spans[5] == (date(2026, 3, 28), date(2026, 4, 11))
    assert [p.is_milestone for p in planned] == [False, False, True, False, True, False]
    assert planned[0].name == "Study & scoping"


def test_template_tasks_never_end_before_they_start_even_on_a_tiny_span() -> None:
    for span in (0, 1, 2, 3, 7):
        end = date.fromordinal(date(2026, 1, 1).toordinal() + span)
        for task in t.tasks_from_template(DESIGN_PHASES, date(2026, 1, 1), end):
            assert date(2026, 1, 1) <= task.planned_start <= task.planned_end <= end


def test_an_inverted_span_is_treated_as_one_day() -> None:
    planned = t.tasks_from_template(DESIGN_PHASES, date(2026, 1, 10), date(2026, 1, 1))
    assert {p.planned_start for p in planned} == {date(2026, 1, 10)}
