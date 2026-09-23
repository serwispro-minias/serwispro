from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.catalog_part import InventoryItem


class VatRate(BaseTenantModel):
    """VAT dictionary managed by the administrator, shared by warehouse products."""

    __tablename__ = "vat_rates"
    __table_args__ = (
        CheckConstraint("rate >= 0", name="ck_vat_rates_rate_non_negative"),
        Index("ix_vat_rates_company_id", "company_id"),
        Index("ix_vat_rates_branch_id", "branch_id"),
        Index("ix_vat_rates_code", "code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("23"))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    inventory_items: Mapped[list["InventoryItem"]] = relationship("InventoryItem", back_populates="vat", lazy="select")

    def __repr__(self) -> str:
        return f"<VatRate id={self.id} code={self.code} rate={self.rate}>"
