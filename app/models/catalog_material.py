from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.catalog_category import CatalogCategory
    from app.models.catalog_manufacturer import CatalogManufacturer
    from app.models.catalog_stock_movement import CatalogStockMovement
    from app.models.catalog_supplier import CatalogSupplier
    from app.models.service_order_material_usage import ServiceOrderMaterialUsage


class CatalogMaterial(BaseTenantModel):
    """Consumable material with stock and movement support."""

    __tablename__ = "catalog_materials"
    __table_args__ = (
        Index("ix_catalog_materials_company_id", "company_id"),
        Index("ix_catalog_materials_branch_id", "branch_id"),
        Index("ix_catalog_materials_code", "code"),
        Index("ix_catalog_materials_name", "name"),
        Index("ix_catalog_materials_category_id", "category_id"),
        Index("ix_catalog_materials_supplier_id", "supplier_id"),
        Index("ix_catalog_materials_manufacturer_id", "manufacturer_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="szt.")
    current_stock: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    minimum_stock: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    purchase_price_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    default_usage_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("1"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("23"))
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    auto_issue_on_order: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    category_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_categories.id"), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_suppliers.id"), nullable=True)
    manufacturer_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_manufacturers.id"), nullable=True)

    category: Mapped["CatalogCategory | None"] = relationship("CatalogCategory", back_populates="materials", lazy="select")
    supplier: Mapped["CatalogSupplier | None"] = relationship("CatalogSupplier", back_populates="materials", lazy="select")
    manufacturer: Mapped["CatalogManufacturer | None"] = relationship("CatalogManufacturer", back_populates="materials", lazy="select")
    movements: Mapped[list["CatalogStockMovement"]] = relationship(
        "CatalogStockMovement",
        back_populates="material",
        lazy="select",
    )
    usages: Mapped[list["ServiceOrderMaterialUsage"]] = relationship(
        "ServiceOrderMaterialUsage",
        back_populates="material",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<CatalogMaterial id={self.id} code={self.code}>"
