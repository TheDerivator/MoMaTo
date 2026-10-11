"""Project statuses and priorities: the fixed vocabularies of the core project fields (D-018)."""

from enum import StrEnum


class ProjectStatus(StrEnum):
    """In the fixed order of the status chips. Any transition is allowed (D-018)."""

    IDEA = "idea"
    REJECTED = "rejected"
    PREPARATION = "preparation"
    PROGRESS = "progress"
    HOLD = "hold"
    STOPPED = "stopped"
    FINISHED = "finished"


STATUS_LABELS: dict[ProjectStatus, str] = {
    ProjectStatus.IDEA: "Idea",
    ProjectStatus.REJECTED: "Rejected idea",
    ProjectStatus.PREPARATION: "In preparation",
    ProjectStatus.PROGRESS: "In progress",
    ProjectStatus.HOLD: "On hold",
    ProjectStatus.STOPPED: "Stopped",
    ProjectStatus.FINISHED: "Finished",
}

# The design's status hues; "rejected" is drawn desaturated.
STATUS_HUES: dict[ProjectStatus, int] = {
    ProjectStatus.IDEA: 90,
    ProjectStatus.REJECTED: 285,
    ProjectStatus.PREPARATION: 235,
    ProjectStatus.PROGRESS: 155,
    ProjectStatus.HOLD: 60,
    ProjectStatus.STOPPED: 20,
    ProjectStatus.FINISHED: 305,
}

DEFAULT_HIDDEN_STATUSES = (ProjectStatus.STOPPED,)

# The statuses a person can book time on through "+ Add project" (TS-8).
BOOKABLE_STATUSES = (ProjectStatus.PREPARATION, ProjectStatus.PROGRESS)


class Priority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


PRIORITY_LABELS: dict[Priority, str] = {
    Priority.HIGH: "High",
    Priority.MEDIUM: "Medium",
    Priority.LOW: "Low",
}

DEFAULT_PRIORITY = Priority.MEDIUM
