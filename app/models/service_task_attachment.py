from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.service_task import ServiceTask
    from app.models.user import User


class ServiceTaskAttachment(BaseTenantModel):
    __tablename__ = "service_task_attachments"
    __table_args__ = (
        Index("ix_service_task_attachments_company_id", "company_id"),
        Index("ix_service_task_attachments_branch_id", "branch_id"),
        Index("ix_service_task_attachments_task_id", "service_task_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_task_id: Mapped[int] = mapped_column(ForeignKey("service_tasks.id"), nullable=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    task: Mapped["ServiceTask"] = relationship("ServiceTask", back_populates="attachments")
    uploader: Mapped["User | None"] = relationship("User", lazy="select")
