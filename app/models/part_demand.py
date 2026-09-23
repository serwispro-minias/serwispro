from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.catalog_part import InventoryItem
    from app.models.service_order import ServiceOrder
    from app.models.service_order_item import ServiceOrderItem


class PartDemandStatusEnum(str, PyEnum):
    NEW = "NEW"
    TO_ORDER = "TO_ORDER"
    IN_PURCHASE = "IN_PURCHASE"
    ORDERED = "ORDERED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class PartDemandPriorityEnum(str, PyEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


PART_DEMAND_STATUS_CHOICES: list[tuple[str, str]] = [
    (PartDemandStatusEnum.NEW.value, "Nowe"),
    (PartDemandStatusEnum.TO_ORDER.value, "Do zamówienia"),
    (PartDemandStatusEnum.IN_PURCHASE.value, "W trakcie zakupu"),
    (PartDemandStatusEnum.ORDERED.value, "Zamówione"),
    (PartDemandStatusEnum.DELIVERED.value, "Dostarczone"),
    (PartDemandStatusEnum.CANCELLED.value, "Anulowane"),
]

PART_DEMAND_PRIORITY_CHOICES: list[tuple[str, str]] = [
    (PartDemandPriorityEnum.LOW.value, "Niski"),
    (PartDemandPriorityEnum.NORMAL.value, "Normalny"),
    (PartDemandPriorityEnum.HIGH.value, "Wysoki"),
    (PartDemandPriorityEnum.URGENT.value, "Pilny"),
]

PART_DEMAND_STATUS_LABELS = dict(PART_DEMAND_STATUS_CHOICES)
PART_DEMAND_PRIORITY_LABELS = dict(PART_DEMAND_PRIORITY_CHOICES)


class PartDemand(BaseTenantModel):
    """Demand record for missing parts required by service orders."""

    __tablename__ = "part_demands"
    __table_args__ = (
        Index("ix_part_demands_company_id", "company_id"),
        Index("ix_part_demands_branch_id", "branch_id"),
        Index("ix_part_demands_order_id", "service_order_id"),
        Index("ix_part_demands_order_item_id", "service_order_item_id"),
        Index("ix_part_demands_inventory_item_id", "inventory_item_id"),
        Index("ix_part_demands_status", "status"),
        Index("ix_part_demands_priority", "priority"),
        Index("ix_part_demands_expected_date", "expected_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_order_id: Mapped[int] = mapped_column(ForeignKey("service_orders.id"), nullable=False)
    service_order_item_id: Mapped[int | None] = mapped_column(ForeignKey("service_order_items.id"), nullable=True)
    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), nullable=False)

    requested_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    reserved_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    missing_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))

    status: Mapped[str] = mapped_column(String(24), nullable=False, default=PartDemandStatusEnum.NEW.value)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default=PartDemandPriorityEnum.NORMAL.value)
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    service_order: Mapped["ServiceOrder"] = relationship("ServiceOrder", back_populates="part_demands", lazy="select")
    service_order_item: Mapped["ServiceOrderItem | None"] = relationship("ServiceOrderItem", back_populates="part_demands", lazy="select")
    inventory_item: Mapped["InventoryItem"] = relationship("InventoryItem", lazy="select")

    def __repr__(self) -> str:
        return f"<PartDemand id={self.id} order_id={self.service_order_id} part_id={self.inventory_item_id}>"
