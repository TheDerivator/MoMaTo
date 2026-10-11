"""The organisation tree: nodes of any depth; some are flagged as departments (D-006)."""

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from momato.db.base import Base, Name


class OrgNode(Base):
    """A node of the tree. Exactly one has no parent (the root); the org editor keeps it so.

    No ON DELETE CASCADE (MS SQL forbids it on self-references): a node can only be deleted when
    nothing refers to it, which the service checks and the foreign keys enforce.
    """

    __tablename__ = "org_nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("org_nodes.id"), index=True)
    name: Mapped[str] = mapped_column(Name)
    position: Mapped[int] = mapped_column(default=0)  # order among siblings
    is_department: Mapped[bool] = mapped_column(default=False)
