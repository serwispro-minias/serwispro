from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.service_task import ServiceTask
    from app.models.user import User


class ServiceTaskComment(BaseTenantModel):
    __tablename__ = "service_task_comments"
    __table_args__ = (
        Index("ix_service_task_comments_company_id", "company_id"),
        Index("ix_service_task_comments_branch_id", "branch_id"),
        Index("ix_service_task_comments_task_id", "service_task_id"),
        Index("ix_service_task_comments_author_id", "author_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_task_id: Mapped[int] = mapped_column(ForeignKey("service_tasks.id"), nullable=False)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    task: Mapped["ServiceTask"] = relationship("ServiceTask", back_populates="comments")
    author: Mapped["User | None"] = relationship("User", lazy="select")
