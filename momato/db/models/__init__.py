"""All tables. Importing this package registers every model on `Base.metadata`."""

from momato.db.base import Base
from momato.db.models.conversation import Attachment, Post, PostRevision
from momato.db.models.identity import (
    ApiToken,
    AuditEntry,
    DefaultGrant,
    ExternalIdentity,
    GroupRoleMapping,
    LoginAttempt,
    Role,
    RoleAssignment,
    RolePermission,
    SsoRequest,
    UserSession,
)
from momato.db.models.log import LogEntry
from momato.db.models.org import OrgNode
from momato.db.models.people import Availability, User, UserKind, UserStatus
from momato.db.models.plans import ActionPlan, ActionPlanProject
from momato.db.models.projects import PlannedDays, Project, ProjectDetail, ProjectMember, Task
from momato.db.models.system import AppLock, AppState
from momato.db.models.time import TimeEntry, WeekSubmission

__all__ = [
    "ActionPlan",
    "ActionPlanProject",
    "ApiToken",
    "AppLock",
    "AppState",
    "Attachment",
    "AuditEntry",
    "Availability",
    "Base",
    "DefaultGrant",
    "ExternalIdentity",
    "GroupRoleMapping",
    "LogEntry",
    "LoginAttempt",
    "OrgNode",
    "PlannedDays",
    "Post",
    "PostRevision",
    "Project",
    "ProjectDetail",
    "ProjectMember",
    "Role",
    "RoleAssignment",
    "RolePermission",
    "SsoRequest",
    "Task",
    "TimeEntry",
    "User",
    "UserKind",
    "UserSession",
    "UserStatus",
    "WeekSubmission",
]
