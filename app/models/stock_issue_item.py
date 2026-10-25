from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.catalog_part import InventoryItem
    from app.models.part_demand import PartDemand
    from app.models.service_order_part_reservation import ServiceOrderPartReservation
    from app.models.stock_issue import StockIssue


class StockIssueItem(BaseModel):
    __tablename__ = "stock_issue_items"
    __table_args__ = (
        Index("ix_stock_issue_items_issue_id", "stock_issue_id"),
        Index("ix_stock_issue_items_inventory_item_id", "inventory_item_id"),
        Index("ix_stock_issue_items_demand_id", "part_demand_id"),
        Index("ix_stock_issue_items_reservation_id", "reservation_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_issue_id: Mapped[int] = mapped_column(ForeignKey("stock_issues.id"), nullable=False)
    inventory_item_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_items.id"), nullable=True)
    material_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_materials.id"), nullable=True)
    service_order_item_id: Mapped[int | None] = mapped_column(ForeignKey("service_order_items.id"), nullable=True)
    settlement_version: Mapped[int | None] = mapped_column(nullable=True)
    part_demand_id: Mapped[int | None] = mapped_column(ForeignKey("part_demands.id"), nullable=True)
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("service_order_part_reservations.id"), nullable=True)
    quantity_issued: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)

    stock_issue: Mapped["StockIssue"] = relationship("StockIssue", back_populates="items", lazy="select")
    inventory_item: Mapped["InventoryItem"] = relationship("InventoryItem", lazy="select")
    material = relationship("CatalogMaterial", lazy="select")
    order_item = relationship("ServiceOrderItem", lazy="select")
    demand: Mapped["PartDemand | None"] = relationship("PartDemand", lazy="select")
    reservation: Mapped["ServiceOrderPartReservation"] = relationship("ServiceOrderPartReservation", lazy="select")

