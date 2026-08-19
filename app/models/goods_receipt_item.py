from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.catalog_part import CatalogPart
    from app.models.goods_receipt import GoodsReceipt
    from app.models.purchase_order_item import PurchaseOrderItem


class GoodsReceiptItem(BaseModel):
    __tablename__ = "goods_receipt_items"
    __table_args__ = (
        Index("ix_goods_receipt_items_receipt_id", "goods_receipt_id"),
        Index("ix_goods_receipt_items_part_id", "part_id"),
        Index("ix_goods_receipt_items_purchase_order_item_id", "purchase_order_item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    goods_receipt_id: Mapped[int] = mapped_column(ForeignKey("goods_receipts.id"), nullable=False)
    purchase_order_item_id: Mapped[int] = mapped_column(ForeignKey("purchase_order_items.id"), nullable=False)
    part_id: Mapped[int] = mapped_column(ForeignKey("catalog_parts.id"), nullable=False)
    quantity_ordered: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    purchase_price_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    batch_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(180), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    goods_receipt: Mapped["GoodsReceipt"] = relationship("GoodsReceipt", back_populates="items", lazy="select")
    purchase_order_item: Mapped["PurchaseOrderItem"] = relationship("PurchaseOrderItem", lazy="select")
    part: Mapped["CatalogPart"] = relationship("CatalogPart", lazy="select")