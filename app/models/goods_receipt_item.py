from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.catalog_part import InventoryItem
    from app.models.goods_receipt import GoodsReceipt
    from app.models.part_demand import PartDemand
    from app.models.purchase_order_item import PurchaseOrderItem
    from app.models.vat_rate import VatRate


class GoodsReceiptItem(BaseModel):
    __tablename__ = "goods_receipt_items"
    __table_args__ = (
        Index("ix_goods_receipt_items_receipt_id", "goods_receipt_id"),
        Index("ix_goods_receipt_items_inventory_item_id", "inventory_item_id"),
        Index("ix_goods_receipt_items_purchase_order_item_id", "purchase_order_item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    goods_receipt_id: Mapped[int] = mapped_column(ForeignKey("goods_receipts.id"), nullable=False)
    purchase_order_item_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_order_items.id"), nullable=True)
    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), nullable=False)
    quantity_ordered: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    purchase_price_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    sale_price_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    vat_id: Mapped[int | None] = mapped_column(ForeignKey("vat_rates.id"), nullable=True)
    demand_id: Mapped[int | None] = mapped_column(ForeignKey("part_demands.id"), nullable=True)
    batch_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(180), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    goods_receipt: Mapped["GoodsReceipt"] = relationship("GoodsReceipt", back_populates="items", lazy="select")
    purchase_order_item: Mapped["PurchaseOrderItem"] = relationship("PurchaseOrderItem", lazy="select")
    inventory_item: Mapped["InventoryItem"] = relationship("InventoryItem", lazy="select")
    vat: Mapped["VatRate | None"] = relationship("VatRate", lazy="select")
    demand: Mapped["PartDemand | None"] = relationship("PartDemand", lazy="select")
