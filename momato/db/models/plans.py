"""Action plans: owned by one org node, grouping projects from any department (AP-1)."""

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from momato.db.base import Base, Name, Text


class ActionPlan(Base):
    __tablename__ = "action_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Name)
    description: Mapped[str] = mapped_column(Text, default="")
    owner_org_node_id: Mapped[int] = mapped_column(ForeignKey("org_nodes.id"), index=True)
    coordinator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    hue: Mapped[int] = mapped_column(default=285)  # from a fixed palette
    position: Mapped[int] = mapped_column(default=0)
    version: Mapped[int] = mapped_column(default=1)


class ActionPlanProject(Base):
    __tablename__ = "action_plan_projects"

    plan_id: Mapped[int] = mapped_column(ForeignKey("action_plans.id"), primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), primary_key=True, index=True)
