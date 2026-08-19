from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.catalog_part import CatalogPart
    from app.models.purchase_order import PurchaseOrder
    from app.models.purchase_order_demand_link import PurchaseOrderDemandLink


class PurchaseOrderItem(BaseModel):
    __tablename__ = "purchase_order_items"
    __table_args__ = (Index("ix_purchase_order_items_order_id", "purchase_order_id"), Index("ix_purchase_order_items_part_id", "part_id"))

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), nullable=False)
    part_id: Mapped[int] = mapped_column(ForeignKey("catalog_parts.id"), nullable=False)
    code_snapshot: Mapped[str] = mapped_column(String(80), nullable=False)
    manufacturer_snapshot: Mapped[str | None] = mapped_column(String(180), nullable=True)
    quantity_ordered: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="szt.")
    unit_price_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("23"))
    total_net: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))
    total_vat: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))
    total_gross: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="items", lazy="select")
    part: Mapped["CatalogPart"] = relationship("CatalogPart", lazy="select")
    demand_links: Mapped[list["PurchaseOrderDemandLink"]] = relationship("PurchaseOrderDemandLink", back_populates="purchase_order_item", cascade="all, delete-orphan", lazy="select")