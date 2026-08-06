from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.catalog_material import CatalogMaterial
    from app.models.catalog_stock_movement import CatalogStockMovement
    from app.models.service_order import ServiceOrder


class ServiceOrderMaterialUsage(BaseTenantModel):
    """Usage rows of materials consumed during repair."""

    __tablename__ = "service_order_material_usages"
    __table_args__ = (
        Index("ix_so_mat_usage_company_id", "company_id"),
        Index("ix_so_mat_usage_branch_id", "branch_id"),
        Index("ix_so_mat_usage_order_id", "service_order_id"),
        Index("ix_so_mat_usage_material_id", "material_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_order_id: Mapped[int] = mapped_column(ForeignKey("service_orders.id"), nullable=False)
    material_id: Mapped[int] = mapped_column(ForeignKey("catalog_materials.id"), nullable=False)
    stock_movement_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_stock_movements.id"), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_net_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    net_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    vat_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    gross_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    service_order: Mapped["ServiceOrder"] = relationship("ServiceOrder", lazy="select")
    material: Mapped["CatalogMaterial"] = relationship("CatalogMaterial", back_populates="usages", lazy="select")
    stock_movement: Mapped["CatalogStockMovement | None"] = relationship("CatalogStockMovement", lazy="select")

    def __repr__(self) -> str:
        return f"<ServiceOrderMaterialUsage id={self.id} order_id={self.service_order_id} material_id={self.material_id}>"
