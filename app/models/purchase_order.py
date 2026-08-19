from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.catalog_supplier import CatalogSupplier
    from app.models.purchase_order_history import PurchaseOrderHistory
    from app.models.purchase_order_item import PurchaseOrderItem


class PurchaseOrderStatusEnum(str, PyEnum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    CONFIRMED = "CONFIRMED"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


PURCHASE_ORDER_STATUS_CHOICES = [
    ("DRAFT", "Robocze"),
    ("SENT", "Wysłane"),
    ("CONFIRMED", "Potwierdzone"),
    ("PARTIAL", "Częściowo zrealizowane"),
    ("COMPLETED", "Zrealizowane"),
    ("CANCELLED", "Anulowane"),
]
PURCHASE_ORDER_STATUS_LABELS = dict(PURCHASE_ORDER_STATUS_CHOICES)


class PurchaseOrder(BaseTenantModel):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        Index("ix_purchase_orders_company_id", "company_id"),
        Index("ix_purchase_orders_branch_id", "branch_id"),
        Index("ix_purchase_orders_supplier_id", "supplier_id"),
        Index("ix_purchase_orders_status", "status"),
        Index("ix_purchase_orders_order_date", "order_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("catalog_suppliers.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=PurchaseOrderStatusEnum.DRAFT.value)
    order_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_net: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))
    total_vat: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))
    total_gross: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))

    supplier: Mapped["CatalogSupplier"] = relationship("CatalogSupplier", lazy="select")
    items: Mapped[list["PurchaseOrderItem"]] = relationship("PurchaseOrderItem", back_populates="purchase_order", cascade="all, delete-orphan", lazy="select")
    history: Mapped[list["PurchaseOrderHistory"]] = relationship("PurchaseOrderHistory", back_populates="purchase_order", cascade="all, delete-orphan", order_by="PurchaseOrderHistory.changed_at.asc()", lazy="select")
