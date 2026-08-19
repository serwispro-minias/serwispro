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
    from app.models.part_demand import PartDemand
    from app.models.purchase_request import PurchaseRequest
    from app.models.catalog_supplier import CatalogSupplier
    from app.models.service_order_part_reservation import ServiceOrderPartReservation


class CatalogPart(BaseTenantModel):
    """Warehouse part with stock and movement support."""

    __tablename__ = "catalog_parts"
    __table_args__ = (
        Index("ix_catalog_parts_company_id", "company_id"),
        Index("ix_catalog_parts_branch_id", "branch_id"),
        Index("ix_catalog_parts_code", "code"),
        Index("ix_catalog_parts_name", "name"),
        Index("ix_catalog_parts_category_id", "category_id"),
        Index("ix_catalog_parts_supplier_id", "supplier_id"),
        Index("ix_catalog_parts_preferred_supplier_id", "preferred_supplier_id"),
        Index("ix_catalog_parts_manufacturer_id", "manufacturer_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="szt.")
    current_stock: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    minimum_stock: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    purchase_price_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    sale_price_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("23"))
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_sellable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_reservable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    category_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_categories.id"), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_suppliers.id"), nullable=True)
    preferred_supplier_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_suppliers.id"), nullable=True)
    manufacturer_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_manufacturers.id"), nullable=True)

    category: Mapped["CatalogCategory | None"] = relationship("CatalogCategory", back_populates="parts", lazy="select")
    supplier: Mapped["CatalogSupplier | None"] = relationship("CatalogSupplier", back_populates="parts", foreign_keys=[supplier_id], lazy="select")
    preferred_supplier: Mapped["CatalogSupplier | None"] = relationship("CatalogSupplier", foreign_keys=[preferred_supplier_id], lazy="select")
    manufacturer: Mapped["CatalogManufacturer | None"] = relationship("CatalogManufacturer", back_populates="parts", lazy="select")
    movements: Mapped[list["CatalogStockMovement"]] = relationship(
        "CatalogStockMovement",
        back_populates="part",
        lazy="select",
    )
    reservations: Mapped[list["ServiceOrderPartReservation"]] = relationship(
        "ServiceOrderPartReservation",
        back_populates="part",
        lazy="select",
    )
    part_demands: Mapped[list["PartDemand"]] = relationship("PartDemand", back_populates="inventory_item", lazy="select")
    purchase_requests: Mapped[list["PurchaseRequest"]] = relationship("PurchaseRequest", back_populates="part", lazy="select")

    def __repr__(self) -> str:
        return f"<CatalogPart id={self.id} code={self.code}>"
