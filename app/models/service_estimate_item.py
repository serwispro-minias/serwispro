from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.service_estimate import ServiceEstimate


SERVICE_ESTIMATE_ITEM_SOURCE_CHOICES: list[tuple[str, str]] = [
    ("PART", "Część"),
    ("MATERIAL", "Materiał"),
    ("SERVICE", "Usługa"),
    ("MANUAL", "Własna pozycja"),
]

SERVICE_ESTIMATE_ITEM_SOURCE_LABELS = dict(SERVICE_ESTIMATE_ITEM_SOURCE_CHOICES)


class ServiceEstimateItem(BaseTenantModel):
    """Snapshot line on a repair estimate version."""

    __tablename__ = "service_estimate_items"
    __table_args__ = (
        Index("ix_service_estimate_items_company_id", "company_id"),
        Index("ix_service_estimate_items_branch_id", "branch_id"),
        Index("ix_service_estimate_items_estimate_id", "estimate_id"),
        Index("ix_service_estimate_items_source_type", "source_type"),
        Index("ix_service_estimate_items_sort_order", "sort_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    estimate_id: Mapped[int] = mapped_column(ForeignKey("service_estimates.id"), nullable=False)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[int | None] = mapped_column(nullable=True)
    code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="szt.")
    unit_net_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("23"))
    net_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    vat_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    gross_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    estimate: Mapped["ServiceEstimate"] = relationship("ServiceEstimate", back_populates="items", lazy="select")

    def __repr__(self) -> str:
        return f"<ServiceEstimateItem id={self.id} estimate_id={self.estimate_id} name={self.name!r}>"