from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.service_order import ServiceOrder
    from app.models.user import User


SERVICE_ORDER_ACTION_TYPE_CHOICES: list[tuple[str, str]] = [
    ("DIAGNOSIS", "diagnoza"),
    ("CUSTOMER_CONTACT", "kontakt z klientem"),
    ("REPAIR", "naprawa"),
    ("PART_REPLACEMENT", "wymiana części"),
    ("TESTS", "testy"),
    ("SOFTWARE_UPDATE", "aktualizacja oprogramowania"),
    ("CLEANING", "czyszczenie"),
    ("DEVICE_RELEASE", "wydanie sprzętu"),
    ("OTHER", "inne"),
]

SERVICE_ORDER_ACTION_TYPE_LABELS = dict(SERVICE_ORDER_ACTION_TYPE_CHOICES)


class ServiceOrderAction(BaseTenantModel):
    """Repair/action history entry attached to a service order."""

    __tablename__ = "service_order_actions"
    __table_args__ = (
        Index("ix_service_order_actions_order_id", "service_order_id"),
        Index("ix_service_order_actions_action_date", "action_date"),
        Index("ix_service_order_actions_technician_id", "technician_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_order_id: Mapped[int] = mapped_column(ForeignKey("service_orders.id"), nullable=False)
    action_date: Mapped[date] = mapped_column(Date, nullable=False)
    technician_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    work_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    is_visible_for_customer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    service_order: Mapped["ServiceOrder"] = relationship("ServiceOrder", back_populates="actions")
    technician: Mapped["User | None"] = relationship("User", lazy="select")

    def __repr__(self) -> str:
        return f"<ServiceOrderAction id={self.id} order_id={self.service_order_id} type={self.action_type}>"
