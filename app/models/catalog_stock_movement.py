from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.catalog_material import CatalogMaterial
    from app.models.catalog_part import CatalogPart
    from app.models.user import User


CATALOG_ITEM_TYPE_CHOICES: list[tuple[str, str]] = [
    ("PART", "Część"),
    ("MATERIAL", "Materiał"),
]

CATALOG_MOVEMENT_TYPE_CHOICES: list[tuple[str, str]] = [
    ("RECEIPT", "Przyjęcie"),
    ("ISSUE", "Wydanie"),
    ("ADJUSTMENT", "Korekta"),
    ("RESERVATION", "Rezerwacja"),
    ("RELEASE", "Zwolnienie rezerwacji"),
    ("SALE", "Sprzedaż"),
    ("AUTO_ISSUE", "Automatyczne odpisanie"),
]

CATALOG_MOVEMENT_TYPE_LABELS = dict(CATALOG_MOVEMENT_TYPE_CHOICES)


class CatalogStockMovement(BaseTenantModel):
    """Movement ledger for parts/materials."""

    __tablename__ = "catalog_stock_movements"
    __table_args__ = (
        Index("ix_catalog_movements_company_id", "company_id"),
        Index("ix_catalog_movements_branch_id", "branch_id"),
        Index("ix_catalog_movements_item_type", "item_type"),
        Index("ix_catalog_movements_part_id", "part_id"),
        Index("ix_catalog_movements_material_id", "material_id"),
        Index("ix_catalog_movements_order_id", "service_order_id"),
        Index("ix_catalog_movements_created_at", "operation_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    part_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_parts.id"), nullable=True)
    material_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_materials.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    service_order_id: Mapped[int | None] = mapped_column(ForeignKey("service_orders.id"), nullable=True)
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    operation_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    stock_before: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    stock_after: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    part: Mapped["CatalogPart | None"] = relationship("CatalogPart", back_populates="movements", lazy="select")
    material: Mapped["CatalogMaterial | None"] = relationship("CatalogMaterial", back_populates="movements", lazy="select")
    user: Mapped["User | None"] = relationship("User", lazy="select")

    def __repr__(self) -> str:
        return f"<CatalogStockMovement id={self.id} type={self.movement_type} item_type={self.item_type}>"
