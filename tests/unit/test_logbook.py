"""Which logbook entries a change of the core project fields produces."""

from dataclasses import replace
from datetime import date

import pytest

from momato.domain import logbook as lb

BASE = lb.CoreSnapshot(
    title="Sensor retrofit on conveyor 4",
    status="In progress",
    start_date=date(2025, 11, 3),
    end_date=date(2027, 3, 31),
    coordinator="Tomás Rivera",
    org_node="Automation & data",
    priority="Medium",
    goal="Replace the end-of-life sensors.",
    people={1: "Tomás Rivera", 2: "Anouk Smit"},
    action_plans={10: "Digital plant"},
)


def test_an_unchanged_project_produces_no_entries() -> None:
    assert lb.diff_core(BASE, replace(BASE)) == []


def test_creation_is_one_entry() -> None:
    """[LB-1 detail]"""
    assert lb.creation_entry() == lb.LogEntry(lb.LogField.CREATED, None, "Created")


@pytest.mark.parametrize(
    ("change", "field", "old", "new"),
    [
        (
            {"title": "Conveyor 4 sensors"},
            lb.LogField.TITLE,
            "Sensor retrofit on conveyor 4",
            "Conveyor 4 sensors",
        ),
        ({"status": "On hold"}, lb.LogField.STATUS, "In progress", "On hold"),
        ({"start_date": date(2025, 12, 1)}, lb.LogField.START_DATE, "3 Nov 2025", "1 Dec 2025"),
        ({"end_date": date(2027, 6, 30)}, lb.LogField.END_DATE, "31 Mar 2027", "30 Jun 2027"),
        ({"coordinator": "Anouk Smit"}, lb.LogField.COORDINATOR, "Tomás Rivera", "Anouk Smit"),
        ({"org_node": "Energy"}, lb.LogField.ORG_NODE, "Automation & data", "Energy"),
        ({"priority": "High"}, lb.LogField.PRIORITY, "Medium", "High"),
        (
            {"goal": "A new goal."},
            lb.LogField.GOAL,
            "Replace the end-of-life sensors.",
            "A new goal.",
        ),
    ],
)
def test_each_core_field_logs_one_entry_with_old_and_new_value(
    change: dict[str, object], field: lb.LogField, old: str, new: str
) -> None:
    entries = lb.diff_core(BASE, replace(BASE, **change))  # pyright: ignore[reportArgumentType]
    assert entries == [lb.LogEntry(field, old, new)]


def test_people_added_and_removed_get_one_entry_each_in_alphabetical_order() -> None:
    changed = replace(BASE, people={1: "Tomás Rivera", 3: "Sofia Lind", 4: "Pieter Kools"})
    assert lb.diff_core(BASE, changed) == [
        lb.LogEntry(lb.LogField.PEOPLE, None, "Added Pieter Kools"),
        lb.LogEntry(lb.LogField.PEOPLE, None, "Added Sofia Lind"),
        lb.LogEntry(lb.LogField.PEOPLE, None, "Removed Anouk Smit"),
    ]


def test_a_renamed_person_is_not_a_change_of_people() -> None:
    assert lb.diff_core(BASE, replace(BASE, people={1: "Tomás Rivera-Diaz", 2: "Anouk Smit"})) == []


def test_action_plans_added_and_removed() -> None:
    changed = replace(BASE, action_plans={11: "Energy & resources 2027"})
    assert lb.diff_core(BASE, changed) == [
        lb.LogEntry(lb.LogField.ACTION_PLANS, None, "Added to Energy & resources 2027"),
        lb.LogEntry(lb.LogField.ACTION_PLANS, None, "Removed from Digital plant"),
    ]


def test_several_changes_keep_a_stable_order() -> None:
    changed = replace(
        BASE, status="Finished", title="Done", priority="Low", end_date=date(2027, 1, 1)
    )
    assert [e.field for e in lb.diff_core(BASE, changed)] == [
        lb.LogField.TITLE,
        lb.LogField.STATUS,
        lb.LogField.END_DATE,
        lb.LogField.PRIORITY,
    ]


def test_every_field_has_a_label_and_the_filters_cover_the_design() -> None:
    """[LB-2 detail]"""
    assert set(lb.FIELD_LABELS) == set(lb.LogField)
    assert lb.filter_fields(None) is None
    assert lb.filter_fields("all") is None
    assert lb.filter_fields("dates") == {lb.LogField.START_DATE, lb.LogField.END_DATE}
    assert lb.filter_fields("people") == {lb.LogField.PEOPLE, lb.LogField.COORDINATOR}
    with pytest.raises(ValueError, match="unknown logbook filter"):
        lb.filter_fields("nonsense")


def test_hues_match_the_design() -> None:
    """[LB-3 detail]"""
    assert lb.FIELD_HUES[lb.LogField.TITLE] == 285
    assert lb.FIELD_HUES[lb.LogField.STATUS] == 155
    assert lb.FIELD_HUES[lb.LogField.END_DATE] == 60
    assert lb.FIELD_HUES[lb.LogField.COORDINATOR] == 235
    assert lb.FIELD_HUES[lb.LogField.PEOPLE] == 330
    assert lb.FIELD_HUES[lb.LogField.ACTION_PLANS] == 20
    assert lb.FIELD_HUES[lb.LogField.CREATED] == 90
    assert lb.FIELD_HUES.get(lb.LogField.GOAL, lb.DEFAULT_HUE) == 285
