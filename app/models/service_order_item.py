from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.part_demand import PartDemand
    from app.models.service_order import ServiceOrder


SERVICE_ORDER_ITEM_TYPE_CHOICES: list[tuple[str, str]] = [
    ("PART", "Część"),
    ("MATERIAL", "Materiał"),
    ("SERVICE", "Usługa"),
]

SERVICE_ORDER_ITEM_TYPE_LABELS = dict(SERVICE_ORDER_ITEM_TYPE_CHOICES)


class ServiceOrderItem(BaseTenantModel):
    """Reservation and cost line for service order items."""

    __tablename__ = "service_order_items"
    __table_args__ = (
        Index("ix_service_order_items_company_id", "company_id"),
        Index("ix_service_order_items_branch_id", "branch_id"),
        Index("ix_service_order_items_order_id", "service_order_id"),
        Index("ix_service_order_items_type", "item_type"),
        Index("ix_service_order_items_item_id", "item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_order_id: Mapped[int] = mapped_column(ForeignKey("service_orders.id"), nullable=False)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    item_id: Mapped[int] = mapped_column(nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    reserved_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    used_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    returned_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    unit_price_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("23"))
    total_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    service_order: Mapped["ServiceOrder"] = relationship("ServiceOrder", back_populates="items", lazy="select")
    part_demands: Mapped[list["PartDemand"]] = relationship(
        "PartDemand",
        back_populates="service_order_item",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<ServiceOrderItem id={self.id} order_id={self.service_order_id} type={self.item_type} item_id={self.item_id}>"
