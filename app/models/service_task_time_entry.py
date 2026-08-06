from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.service_task import ServiceTask
    from app.models.user import User


class ServiceTaskTimeEntry(BaseTenantModel):
    __tablename__ = "service_task_time_entries"
    __table_args__ = (
        Index("ix_service_task_time_entries_company_id", "company_id"),
        Index("ix_service_task_time_entries_branch_id", "branch_id"),
        Index("ix_service_task_time_entries_task_id", "service_task_id"),
        Index("ix_service_task_time_entries_user_id", "user_id"),
        Index("ix_service_task_time_entries_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_task_id: Mapped[int] = mapped_column(ForeignKey("service_tasks.id"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped["ServiceTask"] = relationship("ServiceTask", back_populates="time_entries")
    user: Mapped["User | None"] = relationship("User", lazy="select")
