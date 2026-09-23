from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.catalog_category import ProductCategory
    from app.models.catalog_stock_movement import CatalogStockMovement
    from app.models.inventory_reservation import InventoryReservation
    from app.models.inventory_stock_operation import InventoryStockOperation
    from app.models.part_demand import PartDemand
    from app.models.purchase_request import PurchaseRequest
    from app.models.service_order_part_reservation import ServiceOrderPartReservation
    from app.models.service_order_part_usage import ServiceOrderPartUsage
    from app.models.vat_rate import VatRate


class InventoryItem(BaseTenantModel):
    """Single warehouse product record used by every stock-related module."""

    __tablename__ = "inventory_items"
    __table_args__ = (
        CheckConstraint("current_stock >= 0", name="ck_inventory_items_current_stock_non_negative"),
        CheckConstraint("purchase_price_net >= 0", name="ck_inventory_items_purchase_price_non_negative"),
        CheckConstraint("sale_price_net >= 0", name="ck_inventory_items_sale_price_non_negative"),
        Index("ix_catalog_parts_company_id", "company_id"),
        Index("ix_catalog_parts_branch_id", "branch_id"),
        Index("ix_catalog_parts_code", "code"),
        Index("ix_catalog_parts_name", "name"),
        Index("ix_catalog_parts_category_id", "category_id"),
        Index("ix_catalog_parts_vat_id", "vat_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    purchase_price_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    sale_price_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))

    category_id: Mapped[int] = mapped_column(ForeignKey("product_categories.id"), nullable=False)
    vat_id: Mapped[int] = mapped_column(ForeignKey("vat_rates.id"), nullable=False)

    category: Mapped["ProductCategory"] = relationship("ProductCategory", back_populates="inventory_items", lazy="select")
    vat: Mapped["VatRate"] = relationship("VatRate", back_populates="inventory_items", lazy="select")
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
    stock_operations: Mapped[list["InventoryStockOperation"]] = relationship("InventoryStockOperation", back_populates="part", lazy="select")
    inventory_reservations: Mapped[list["InventoryReservation"]] = relationship("InventoryReservation", back_populates="inventory_item", lazy="select")
    order_usages: Mapped[list["ServiceOrderPartUsage"]] = relationship("ServiceOrderPartUsage", back_populates="part", lazy="select")

    def __repr__(self) -> str:
        return f"<InventoryItem id={self.id} code={self.code}>"


CatalogPart = InventoryItem
