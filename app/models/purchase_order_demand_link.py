from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.part_demand import PartDemand
    from app.models.purchase_order_item import PurchaseOrderItem


class PurchaseOrderDemandLink(BaseModel):
    __tablename__ = "purchase_order_demand_links"
    __table_args__ = (Index("ix_po_demand_links_item_id", "purchase_order_item_id"), Index("ix_po_demand_links_demand_id", "part_demand_id"))

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_item_id: Mapped[int] = mapped_column(ForeignKey("purchase_order_items.id"), nullable=False)
    part_demand_id: Mapped[int] = mapped_column(ForeignKey("part_demands.id"), nullable=False)
    allocated_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))

    purchase_order_item: Mapped["PurchaseOrderItem"] = relationship("PurchaseOrderItem", back_populates="demand_links", lazy="select")
    demand: Mapped["PartDemand"] = relationship("PartDemand", lazy="select")