from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.estimate_approval_token import EstimateApprovalToken
    from app.models.service_order import ServiceOrder
    from app.models.service_estimate_item import ServiceEstimateItem


SERVICE_ESTIMATE_STATUS_CHOICES: list[tuple[str, str]] = [
    ("DRAFT", "Roboczy"),
    ("SENT", "Wysłany"),
    ("ACCEPTED", "Zaakceptowany"),
    ("APPROVED", "Zaakceptowany"),
    ("REJECTED", "Odrzucony"),
    ("ARCHIVED", "Archiwalny"),
]

SERVICE_ESTIMATE_STATUS_LABELS = dict(SERVICE_ESTIMATE_STATUS_CHOICES)


class ServiceEstimate(BaseTenantModel):
    """Versioned repair estimate attached to a service order."""

    __tablename__ = "service_estimates"
    __table_args__ = (
        Index("ix_service_estimates_company_id", "company_id"),
        Index("ix_service_estimates_branch_id", "branch_id"),
        Index("ix_service_estimates_order_id", "service_order_id"),
        Index("ix_service_estimates_version_number", "version_number"),
        Index("ix_service_estimates_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_order_id: Mapped[int] = mapped_column(ForeignKey("service_orders.id"), nullable=False)
    parent_estimate_id: Mapped[int | None] = mapped_column(ForeignKey("service_estimates.id"), nullable=True)
    version_number: Mapped[int] = mapped_column(nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Kosztorys naprawy")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    parts_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    materials_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    services_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    net_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    vat_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    gross_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))

    service_order: Mapped["ServiceOrder"] = relationship("ServiceOrder", back_populates="estimates", lazy="select")
    parent_estimate: Mapped["ServiceEstimate | None"] = relationship(
        "ServiceEstimate",
        remote_side="ServiceEstimate.id",
        back_populates="revisions",
        lazy="select",
    )
    revisions: Mapped[list["ServiceEstimate"]] = relationship(
        "ServiceEstimate",
        back_populates="parent_estimate",
        lazy="select",
        cascade="all, delete-orphan",
    )
    items: Mapped[list["ServiceEstimateItem"]] = relationship(
        "ServiceEstimateItem",
        back_populates="estimate",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="ServiceEstimateItem.sort_order.asc(), ServiceEstimateItem.id.asc()",
    )
    approval_tokens: Mapped[list["EstimateApprovalToken"]] = relationship(
        "EstimateApprovalToken",
        back_populates="estimate",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="EstimateApprovalToken.created_at.desc(), EstimateApprovalToken.id.desc()",
    )

    def __repr__(self) -> str:
        return f"<ServiceEstimate id={self.id} order_id={self.service_order_id} version={self.version_number}>"