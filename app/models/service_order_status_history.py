from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.service_order import ServiceOrder
    from app.models.user import User


class ServiceOrderStatusHistory(BaseModel):
    """Represents status transition events for service orders."""

    __tablename__ = "service_order_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_order_id: Mapped[int] = mapped_column(ForeignKey("service_orders.id"), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    new_status: Mapped[str] = mapped_column(String(40), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    service_order: Mapped["ServiceOrder"] = relationship("ServiceOrder", back_populates="status_history")
    changed_by_user: Mapped["User | None"] = relationship("User", lazy="select")

    def __repr__(self) -> str:
        return f"<ServiceOrderStatusHistory id={self.id} order_id={self.service_order_id}>"
