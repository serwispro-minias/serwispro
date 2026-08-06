from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.workflow_transition import WorkflowTransition


class WorkflowStatus(BaseTenantModel):
    __tablename__ = "workflow_statuses"
    __table_args__ = (
        UniqueConstraint("company_id", "branch_id", "code", name="uq_workflow_status_scope_code"),
        Index("ix_workflow_statuses_company_id", "company_id"),
        Index("ix_workflow_statuses_branch_id", "branch_id"),
        Index("ix_workflow_statuses_code", "code"),
        Index("ix_workflow_statuses_sort_order", "sort_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(String(40), nullable=False, default="#6c757d")
    icon: Mapped[str] = mapped_column(String(80), nullable=False, default="bi-circle")
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    is_initial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    outgoing_transitions: Mapped[list["WorkflowTransition"]] = relationship(
        "WorkflowTransition",
        back_populates="from_status",
        foreign_keys="WorkflowTransition.from_status_id",
        lazy="select",
        cascade="all, delete-orphan",
    )
    incoming_transitions: Mapped[list["WorkflowTransition"]] = relationship(
        "WorkflowTransition",
        back_populates="to_status",
        foreign_keys="WorkflowTransition.to_status_id",
        lazy="select",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<WorkflowStatus id={self.id} code={self.code}>"
