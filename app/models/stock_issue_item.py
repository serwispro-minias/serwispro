from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.catalog_part import CatalogPart
    from app.models.part_demand import PartDemand
    from app.models.service_order_part_reservation import ServiceOrderPartReservation
    from app.models.stock_issue import StockIssue


class StockIssueItem(BaseModel):
    __tablename__ = "stock_issue_items"
    __table_args__ = (
        Index("ix_stock_issue_items_issue_id", "stock_issue_id"),
        Index("ix_stock_issue_items_part_id", "part_id"),
        Index("ix_stock_issue_items_demand_id", "part_demand_id"),
        Index("ix_stock_issue_items_reservation_id", "reservation_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_issue_id: Mapped[int] = mapped_column(ForeignKey("stock_issues.id"), nullable=False)
    part_id: Mapped[int] = mapped_column(ForeignKey("catalog_parts.id"), nullable=False)
    part_demand_id: Mapped[int | None] = mapped_column(ForeignKey("part_demands.id"), nullable=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("service_order_part_reservations.id"), nullable=False)
    quantity_issued: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)

    stock_issue: Mapped["StockIssue"] = relationship("StockIssue", back_populates="items", lazy="select")
    part: Mapped["CatalogPart"] = relationship("CatalogPart", lazy="select")
    demand: Mapped["PartDemand | None"] = relationship("PartDemand", lazy="select")
    reservation: Mapped["ServiceOrderPartReservation"] = relationship("ServiceOrderPartReservation", lazy="select")