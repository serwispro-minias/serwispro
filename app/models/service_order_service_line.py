from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.catalog_service_item import CatalogServiceItem
    from app.models.service_order import ServiceOrder


class ServiceOrderServiceLine(BaseTenantModel):
    """Services attached to service orders/cost estimates."""

    __tablename__ = "service_order_service_lines"
    __table_args__ = (
        Index("ix_so_service_line_company_id", "company_id"),
        Index("ix_so_service_line_branch_id", "branch_id"),
        Index("ix_so_service_line_order_id", "service_order_id"),
        Index("ix_so_service_line_service_id", "service_item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_order_id: Mapped[int] = mapped_column(ForeignKey("service_orders.id"), nullable=False)
    service_item_id: Mapped[int] = mapped_column(ForeignKey("catalog_services.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("1"))
    unit_net_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    net_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    vat_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    gross_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(nullable=False, default=0)

    service_order: Mapped["ServiceOrder"] = relationship("ServiceOrder", lazy="select")
    service_item: Mapped["CatalogServiceItem"] = relationship("CatalogServiceItem", back_populates="order_lines", lazy="select")

    def __repr__(self) -> str:
        return f"<ServiceOrderServiceLine id={self.id} order_id={self.service_order_id} service_item_id={self.service_item_id}>"
