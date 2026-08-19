from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.inventory_part import InventoryPart
    from app.models.service_order import ServiceOrder
    from app.models.user import User


class InventoryReservationStatusEnum(str, PyEnum):
    RESERVED = "RESERVED"
    RELEASED = "RELEASED"
    CONSUMED = "CONSUMED"
    CANCELLED = "CANCELLED"


INVENTORY_RESERVATION_STATUS_CHOICES: list[tuple[str, str]] = [
    (InventoryReservationStatusEnum.RESERVED.value, "Zarezerwowane"),
    (InventoryReservationStatusEnum.RELEASED.value, "Zwolnione"),
    (InventoryReservationStatusEnum.CONSUMED.value, "Zużyte"),
    (InventoryReservationStatusEnum.CANCELLED.value, "Anulowane"),
]
INVENTORY_RESERVATION_STATUS_LABELS = dict(INVENTORY_RESERVATION_STATUS_CHOICES)


class InventoryReservation(BaseTenantModel):
    __tablename__ = "inventory_reservations"
    __table_args__ = (
        Index("ix_inventory_reservations_company_id", "company_id"),
        Index("ix_inventory_reservations_branch_id", "branch_id"),
        Index("ix_inventory_reservations_item_id", "inventory_item_id"),
        Index("ix_inventory_reservations_order_id", "service_order_id"),
        Index("ix_inventory_reservations_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventory_parts.id"), nullable=False)
    service_order_id: Mapped[int] = mapped_column(ForeignKey("service_orders.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    reserved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reserved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=InventoryReservationStatusEnum.RESERVED.value)

    inventory_item: Mapped["InventoryPart"] = relationship("InventoryPart", back_populates="reservations", lazy="select")
    service_order: Mapped["ServiceOrder"] = relationship("ServiceOrder", lazy="select")
    user: Mapped["User | None"] = relationship("User", lazy="select")

    def __repr__(self) -> str:
        return f"<InventoryReservation id={self.id} inventory_item_id={self.inventory_item_id} order_id={self.service_order_id}>"
