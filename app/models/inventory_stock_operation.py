from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.inventory_part import InventoryPart
    from app.models.service_order import ServiceOrder
    from app.models.user import User


INVENTORY_OPERATION_TYPE_CHOICES: list[tuple[str, str]] = [
    ("RECEIPT", "Przyjęcie towaru"),
    ("ISSUE", "Wydanie"),
    ("ADJUSTMENT", "Korekta"),
    ("INVENTORY", "Inwentaryzacja"),
    ("SERVICE_USAGE", "Zużycie do zlecenia"),
    ("RETURN", "Zwrot ze zlecenia"),
    ("RESERVATION", "Rezerwacja"),
    ("RESERVATION_RELEASE", "Zwolnienie rezerwacji"),
    ("CONSUMPTION", "Zużycie części"),
    ("AUTO_PURCHASE_REQUEST", "Automatyczne zapotrzebowanie"),
]

INVENTORY_OPERATION_TYPE_LABELS = dict(INVENTORY_OPERATION_TYPE_CHOICES)


class InventoryStockOperation(BaseTenantModel):
    """Immutable warehouse operation history row."""

    __tablename__ = "inventory_stock_operations"
    __table_args__ = (
        Index("ix_inv_ops_company_id", "company_id"),
        Index("ix_inv_ops_branch_id", "branch_id"),
        Index("ix_inv_ops_part_id", "part_id"),
        Index("ix_inv_ops_order_id", "service_order_id"),
        Index("ix_inv_ops_operation_at", "operation_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    service_order_id: Mapped[int | None] = mapped_column(ForeignKey("service_orders.id"), nullable=True)
    operation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    operation_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    stock_before: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    stock_after: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    part: Mapped["InventoryPart"] = relationship("InventoryItem", back_populates="stock_operations")
    user: Mapped["User | None"] = relationship("User", lazy="select")
    service_order: Mapped["ServiceOrder | None"] = relationship("ServiceOrder", lazy="select")

    def __repr__(self) -> str:
        return f"<InventoryStockOperation id={self.id} part_id={self.part_id} type={self.operation_type}>"
