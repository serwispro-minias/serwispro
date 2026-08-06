from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.inventory_stock_operation import InventoryStockOperation
    from app.models.service_order_part_usage import ServiceOrderPartUsage


class InventoryPart(BaseTenantModel):
    """Part/material card entry in warehouse."""

    __tablename__ = "inventory_parts"
    __table_args__ = (
        Index("ix_inventory_parts_company_id", "company_id"),
        Index("ix_inventory_parts_branch_id", "branch_id"),
        Index("ix_inventory_parts_code", "part_code"),
        Index("ix_inventory_parts_name", "name"),
        Index("ix_inventory_parts_catalog_number", "catalog_number"),
        Index("ix_inventory_parts_barcode", "barcode"),
        Index("ix_inventory_parts_manufacturer", "manufacturer"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    part_code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    catalog_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="szt.")
    minimum_stock: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    current_stock: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    purchase_price_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    sale_price_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("23"))
    supplier: Mapped[str | None] = mapped_column(String(180), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_record_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    stock_operations: Mapped[list["InventoryStockOperation"]] = relationship(
        "InventoryStockOperation",
        back_populates="part",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="InventoryStockOperation.operation_at.asc()",
    )
    order_usages: Mapped[list["ServiceOrderPartUsage"]] = relationship(
        "ServiceOrderPartUsage",
        back_populates="part",
        lazy="select",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<InventoryPart id={self.id} code={self.part_code}>"
