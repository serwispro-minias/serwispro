from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.catalog_part import CatalogPart
    from app.models.service_order import ServiceOrder


class ServiceOrderPartReservation(BaseTenantModel):
    """Reservation rows of parts assigned to service orders."""

    __tablename__ = "service_order_part_reservations"
    __table_args__ = (
        Index("ix_so_part_res_company_id", "company_id"),
        Index("ix_so_part_res_branch_id", "branch_id"),
        Index("ix_so_part_res_order_id", "service_order_id"),
        Index("ix_so_part_res_part_id", "part_id"),
        Index("ix_so_part_res_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_order_id: Mapped[int] = mapped_column(ForeignKey("service_orders.id"), nullable=False)
    part_id: Mapped[int] = mapped_column(ForeignKey("catalog_parts.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RESERVED")

    service_order: Mapped["ServiceOrder"] = relationship("ServiceOrder", back_populates="part_reservations", lazy="select")
    part: Mapped["CatalogPart"] = relationship("CatalogPart", back_populates="reservations", lazy="select")

    def __repr__(self) -> str:
        return f"<ServiceOrderPartReservation id={self.id} order_id={self.service_order_id} part_id={self.part_id}>"
