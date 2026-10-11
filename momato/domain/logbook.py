"""The logbook: which entries a change of the core project fields produces (LB-1 to LB-3, D-016).

Entries are generic (field, old value, new value) and hold the values as shown to users, so the
logbook still reads right after a person is renamed. Detail fields, tasks and planned days are
not logged.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from momato.domain.formatting import format_date


class LogField(StrEnum):
    CREATED = "created"
    TITLE = "title"
    STATUS = "status"
    START_DATE = "start_date"
    END_DATE = "end_date"
    COORDINATOR = "coordinator"
    PEOPLE = "people"
    ACTION_PLANS = "action_plans"
    GOAL = "goal"
    PRIORITY = "priority"
    ORG_NODE = "org_node"


FIELD_LABELS: dict[LogField, str] = {
    LogField.CREATED: "Project",
    LogField.TITLE: "Title",
    LogField.STATUS: "Status",
    LogField.START_DATE: "Start date",
    LogField.END_DATE: "End date",
    LogField.COORDINATOR: "Coordinator",
    LogField.PEOPLE: "People",
    LogField.ACTION_PLANS: "Action plans",
    LogField.GOAL: "Goal",
    LogField.PRIORITY: "Priority",
    LogField.ORG_NODE: "Department",
}

# Tint per field (LB-3); the fields not listed use DEFAULT_HUE.
FIELD_HUES: dict[LogField, int] = {
    LogField.TITLE: 285,
    LogField.STATUS: 155,
    LogField.START_DATE: 60,
    LogField.END_DATE: 60,
    LogField.COORDINATOR: 235,
    LogField.PEOPLE: 330,
    LogField.ACTION_PLANS: 20,
    LogField.CREATED: 90,
}
DEFAULT_HUE = 285

# The filter chips of LB-2: Everything shows all fields, the others these.
FILTER_GROUPS: dict[str, frozenset[LogField]] = {
    "title": frozenset({LogField.TITLE}),
    "status": frozenset({LogField.STATUS}),
    "dates": frozenset({LogField.START_DATE, LogField.END_DATE}),
    "people": frozenset({LogField.PEOPLE, LogField.COORDINATOR}),
    "plans": frozenset({LogField.ACTION_PLANS}),
}


@dataclass(frozen=True)
class LogEntry:
    field: LogField
    from_value: str | None
    to_value: str | None


@dataclass(frozen=True)
class CoreSnapshot:
    """The core fields of a project as shown to users; people and plans by id, for comparing."""

    title: str
    status: str  # the status label
    start_date: date
    end_date: date
    coordinator: str  # the name
    org_node: str  # the node's name
    priority: str  # the label
    goal: str
    people: Mapping[int, str]
    action_plans: Mapping[int, str]


def creation_entry() -> LogEntry:
    return LogEntry(LogField.CREATED, None, "Created")


def _changed(field: LogField, old: str, new: str) -> list[LogEntry]:
    return [LogEntry(field, old, new)] if old != new else []


def _membership(
    field: LogField, old: Mapping[int, str], new: Mapping[int, str], added: str, removed: str
) -> list[LogEntry]:
    """One entry per item added or removed, each group in alphabetical order."""
    gone = sorted((name for key, name in old.items() if key not in new), key=str.casefold)
    came = sorted((name for key, name in new.items() if key not in old), key=str.casefold)
    return [LogEntry(field, None, f"{added}{name}") for name in came] + [
        LogEntry(field, None, f"{removed}{name}") for name in gone
    ]


def diff_core(old: CoreSnapshot, new: CoreSnapshot) -> list[LogEntry]:
    """The entries to write when a project goes from `old` to `new`, in a stable order."""
    entries: list[LogEntry] = []
    entries += _changed(LogField.TITLE, old.title, new.title)
    entries += _changed(LogField.STATUS, old.status, new.status)
    entries += _changed(
        LogField.START_DATE, format_date(old.start_date), format_date(new.start_date)
    )
    entries += _changed(LogField.END_DATE, format_date(old.end_date), format_date(new.end_date))
    entries += _changed(LogField.COORDINATOR, old.coordinator, new.coordinator)
    entries += _changed(LogField.ORG_NODE, old.org_node, new.org_node)
    entries += _changed(LogField.PRIORITY, old.priority, new.priority)
    entries += _changed(LogField.GOAL, old.goal, new.goal)
    entries += _membership(LogField.PEOPLE, old.people, new.people, "Added ", "Removed ")
    entries += _membership(
        LogField.ACTION_PLANS, old.action_plans, new.action_plans, "Added to ", "Removed from "
    )
    return entries


def filter_fields(group: str | None) -> frozenset[LogField] | None:
    """The fields of a filter chip, or None for Everything; ValueError for an unknown chip."""
    if group is None or group == "all":
        return None
    try:
        return FILTER_GROUPS[group]
    except KeyError:
        raise ValueError(f"unknown logbook filter {group!r}") from None
