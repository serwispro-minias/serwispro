from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.service_task import ServiceTask
    from app.models.user import User


class ServiceTaskStatusHistory(BaseTenantModel):
    __tablename__ = "service_task_status_history"
    __table_args__ = (
        Index("ix_service_task_status_history_company_id", "company_id"),
        Index("ix_service_task_status_history_branch_id", "branch_id"),
        Index("ix_service_task_status_history_task_id", "service_task_id"),
        Index("ix_service_task_status_history_changed_at", "changed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_task_id: Mapped[int] = mapped_column(ForeignKey("service_tasks.id"), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped["ServiceTask"] = relationship("ServiceTask", back_populates="status_history")
    changed_by_user: Mapped["User | None"] = relationship("User", lazy="select")
