from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.workflow_status import WorkflowStatus


class WorkflowTransition(BaseTenantModel):
    __tablename__ = "workflow_transitions"
    __table_args__ = (
        UniqueConstraint("company_id", "branch_id", "from_status_id", "to_status_id", name="uq_workflow_transition_scope"),
        Index("ix_workflow_transitions_company_id", "company_id"),
        Index("ix_workflow_transitions_branch_id", "branch_id"),
        Index("ix_workflow_transitions_from_status_id", "from_status_id"),
        Index("ix_workflow_transitions_to_status_id", "to_status_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_status_id: Mapped[int] = mapped_column(ForeignKey("workflow_statuses.id"), nullable=False)
    to_status_id: Mapped[int] = mapped_column(ForeignKey("workflow_statuses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    requires_permission: Mapped[str | None] = mapped_column(String(120), nullable=True)
    requires_estimate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_parts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_payment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_sms: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_notification: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    from_status: Mapped["WorkflowStatus"] = relationship(
        "WorkflowStatus",
        back_populates="outgoing_transitions",
        foreign_keys=[from_status_id],
        lazy="select",
    )
    to_status: Mapped["WorkflowStatus"] = relationship(
        "WorkflowStatus",
        back_populates="incoming_transitions",
        foreign_keys=[to_status_id],
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<WorkflowTransition id={self.id} from={self.from_status_id} to={self.to_status_id}>"
