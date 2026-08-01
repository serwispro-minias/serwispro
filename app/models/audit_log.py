from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.user import User


class AuditLog(BaseModel):

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    object_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    user: Mapped["User | None"] = relationship(
        "User",
        back_populates="audit_logs",
    )

    company: Mapped["Company | None"] = relationship(
        "Company",
        back_populates="audit_logs",
    )

    def __repr__(self) -> str:
        return f"<AuditLog action={self.action} user_id={self.user_id}>"
