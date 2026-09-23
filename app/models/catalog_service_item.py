from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.catalog_category import ProductCategory
    from app.models.service_order_service_line import ServiceOrderServiceLine


class CatalogServiceItem(BaseTenantModel):
    """Service dictionary entry used in quotations and service orders."""

    __tablename__ = "catalog_services"
    __table_args__ = (
        Index("ix_catalog_services_company_id", "company_id"),
        Index("ix_catalog_services_branch_id", "branch_id"),
        Index("ix_catalog_services_code", "code"),
        Index("ix_catalog_services_name", "name"),
        Index("ix_catalog_services_category_id", "category_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_price_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("23"))
    standard_duration_minutes: Mapped[int] = mapped_column(nullable=False, default=60)
    is_sellable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    category_id: Mapped[int | None] = mapped_column(ForeignKey("product_categories.id"), nullable=True)

    category: Mapped["ProductCategory | None"] = relationship("ProductCategory", lazy="select")
    order_lines: Mapped[list["ServiceOrderServiceLine"]] = relationship(
        "ServiceOrderServiceLine",
        back_populates="service_item",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<CatalogServiceItem id={self.id} code={self.code}>"
