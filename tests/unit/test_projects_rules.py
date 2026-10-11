"""Project numbers, statuses and priorities. [R4.7]"""

from momato.domain.numbering import next_project_number
from momato.domain.projects import (
    BOOKABLE_STATUSES,
    DEFAULT_HIDDEN_STATUSES,
    DEFAULT_PRIORITY,
    PRIORITY_LABELS,
    STATUS_HUES,
    STATUS_LABELS,
    Priority,
    ProjectStatus,
)


def test_the_next_number_is_the_highest_plus_one_or_the_first() -> None:
    assert next_project_number(None, 1000) == 1000
    assert next_project_number(4340, 1000) == 4341
    assert next_project_number(5, 1000) == 6  # the rule is highest + 1, whatever the first number


def test_the_seven_statuses_come_in_the_design_order_with_labels_and_hues() -> None:
    assert [STATUS_LABELS[s] for s in ProjectStatus] == [
        "Idea",
        "Rejected idea",
        "In preparation",
        "In progress",
        "On hold",
        "Stopped",
        "Finished",
    ]
    assert [STATUS_HUES[s] for s in ProjectStatus] == [90, 285, 235, 155, 60, 20, 305]


def test_stopped_is_hidden_by_default_and_two_statuses_are_bookable() -> None:
    assert DEFAULT_HIDDEN_STATUSES == (ProjectStatus.STOPPED,)
    assert BOOKABLE_STATUSES == (ProjectStatus.PREPARATION, ProjectStatus.PROGRESS)


def test_priorities() -> None:
    assert [PRIORITY_LABELS[p] for p in Priority] == ["High", "Medium", "Low"]
    assert DEFAULT_PRIORITY is Priority.MEDIUM
