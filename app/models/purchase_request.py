from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.catalog_part import InventoryItem
    from app.models.service_order import ServiceOrder


class PurchaseRequestStatusEnum(str, PyEnum):
    NEW = "NEW"
    APPROVED = "APPROVED"
    ORDERED = "ORDERED"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"


class PurchaseRequestPriorityEnum(str, PyEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


PURCHASE_REQUEST_STATUS_CHOICES: list[tuple[str, str]] = [
    (PurchaseRequestStatusEnum.NEW.value, "Nowe"),
    (PurchaseRequestStatusEnum.APPROVED.value, "Zatwierdzone"),
    (PurchaseRequestStatusEnum.ORDERED.value, "Zamówione"),
    (PurchaseRequestStatusEnum.RECEIVED.value, "Odebrane"),
    (PurchaseRequestStatusEnum.CANCELLED.value, "Anulowane"),
]

PURCHASE_REQUEST_PRIORITY_CHOICES: list[tuple[str, str]] = [
    (PurchaseRequestPriorityEnum.LOW.value, "Niski"),
    (PurchaseRequestPriorityEnum.NORMAL.value, "Normalny"),
    (PurchaseRequestPriorityEnum.HIGH.value, "Wysoki"),
    (PurchaseRequestPriorityEnum.URGENT.value, "Pilny"),
]

PURCHASE_REQUEST_STATUS_LABELS = dict(PURCHASE_REQUEST_STATUS_CHOICES)
PURCHASE_REQUEST_PRIORITY_LABELS = dict(PURCHASE_REQUEST_PRIORITY_CHOICES)


class PurchaseRequest(BaseTenantModel):
    """Purchase request collected by technicians and processed by purchasing team."""

    __tablename__ = "purchase_requests"
    __table_args__ = (
        Index("ix_purchase_requests_company_id", "company_id"),
        Index("ix_purchase_requests_branch_id", "branch_id"),
        Index("ix_purchase_requests_service_order_id", "service_order_id"),
        Index("ix_purchase_requests_part_id", "part_id"),
        Index("ix_purchase_requests_status", "status"),
        Index("ix_purchase_requests_priority", "priority"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_order_id: Mapped[int] = mapped_column(ForeignKey("service_orders.id"), nullable=False)
    part_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=PurchaseRequestStatusEnum.NEW.value)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default=PurchaseRequestPriorityEnum.NORMAL.value)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[int | None] = mapped_column(nullable=True)
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    service_order: Mapped["ServiceOrder"] = relationship("ServiceOrder", back_populates="purchase_requests", lazy="select")
    part: Mapped["InventoryItem"] = relationship("InventoryItem", back_populates="purchase_requests", lazy="select")

    def __repr__(self) -> str:
        return f"<PurchaseRequest id={self.id} service_order_id={self.service_order_id} part_id={self.part_id}>"
