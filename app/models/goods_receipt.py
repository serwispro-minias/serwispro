from __future__ import annotations

from datetime import date
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.catalog_supplier import CatalogSupplier
    from app.models.purchase_order import PurchaseOrder
    from app.models.user import User
    from app.models.goods_receipt_item import GoodsReceiptItem


class GoodsReceiptStatusEnum(str, PyEnum):
    NEW = "NEW"
    ACCEPTED = "ACCEPTED"
    CANCELLED = "CANCELLED"


GOODS_RECEIPT_STATUS_CHOICES = [("NEW", "Nowe"), ("ACCEPTED", "Przyjęte"), ("CANCELLED", "Anulowane")]
GOODS_RECEIPT_STATUS_LABELS = dict(GOODS_RECEIPT_STATUS_CHOICES)


class GoodsReceipt(BaseTenantModel):
    __tablename__ = "goods_receipts"
    __table_args__ = (
        Index("ix_goods_receipts_company_id", "company_id"),
        Index("ix_goods_receipts_branch_id", "branch_id"),
        Index("ix_goods_receipts_supplier_id", "supplier_id"),
        Index("ix_goods_receipts_purchase_order_id", "purchase_order_id"),
        Index("ix_goods_receipts_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_number: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("catalog_suppliers.id"), nullable=False)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), nullable=False)
    received_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=GoodsReceiptStatusEnum.NEW.value)

    supplier: Mapped["CatalogSupplier"] = relationship("CatalogSupplier", lazy="select")
    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", lazy="select")
    receiver: Mapped["User | None"] = relationship("User", foreign_keys=[received_by], lazy="select")
    items: Mapped[list["GoodsReceiptItem"]] = relationship("GoodsReceiptItem", back_populates="goods_receipt", cascade="all, delete-orphan", lazy="select")