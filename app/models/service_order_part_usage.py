from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.inventory_part import InventoryPart
    from app.models.inventory_stock_operation import InventoryStockOperation
    from app.models.service_order import ServiceOrder


class ServiceOrderPartUsage(BaseTenantModel):
    """Part consumption attached to service order."""

    __tablename__ = "service_order_part_usages"
    __table_args__ = (
        Index("ix_so_part_usage_company_id", "company_id"),
        Index("ix_so_part_usage_branch_id", "branch_id"),
        Index("ix_so_part_usage_order_id", "service_order_id"),
        Index("ix_so_part_usage_part_id", "part_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_order_id: Mapped[int] = mapped_column(ForeignKey("service_orders.id"), nullable=False)
    part_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), nullable=False)
    stock_operation_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_stock_operations.id"), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_net_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    net_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    vat_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    gross_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    service_order: Mapped["ServiceOrder"] = relationship("ServiceOrder", back_populates="part_usages")
    part: Mapped["InventoryPart"] = relationship("InventoryItem", back_populates="order_usages")
    stock_operation: Mapped["InventoryStockOperation | None"] = relationship("InventoryStockOperation", lazy="select")

    def __repr__(self) -> str:
        return f"<ServiceOrderPartUsage id={self.id} order_id={self.service_order_id} part_id={self.part_id}>"
