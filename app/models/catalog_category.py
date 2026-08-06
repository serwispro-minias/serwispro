from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.catalog_material import CatalogMaterial
    from app.models.catalog_part import CatalogPart
    from app.models.catalog_service_item import CatalogServiceItem


class CatalogCategory(BaseTenantModel):
    """Common category shared by parts, materials and services."""

    __tablename__ = "catalog_categories"
    __table_args__ = (
        Index("ix_catalog_categories_company_id", "company_id"),
        Index("ix_catalog_categories_branch_id", "branch_id"),
        Index("ix_catalog_categories_code", "code"),
        Index("ix_catalog_categories_name", "name"),
        Index("ix_catalog_categories_kind", "kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="ANY")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    parts: Mapped[list["CatalogPart"]] = relationship("CatalogPart", back_populates="category", lazy="select")
    materials: Mapped[list["CatalogMaterial"]] = relationship("CatalogMaterial", back_populates="category", lazy="select")
    services: Mapped[list["CatalogServiceItem"]] = relationship("CatalogServiceItem", back_populates="category", lazy="select")

    def __repr__(self) -> str:
        return f"<CatalogCategory id={self.id} code={self.code}>"
