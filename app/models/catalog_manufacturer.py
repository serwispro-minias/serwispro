from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.catalog_material import CatalogMaterial
    from app.models.catalog_part import CatalogPart


class CatalogManufacturer(BaseTenantModel):
    """Manufacturer shared by parts/materials."""

    __tablename__ = "catalog_manufacturers"
    __table_args__ = (
        Index("ix_catalog_manufacturers_company_id", "company_id"),
        Index("ix_catalog_manufacturers_branch_id", "branch_id"),
        Index("ix_catalog_manufacturers_code", "code"),
        Index("ix_catalog_manufacturers_name", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    parts: Mapped[list["CatalogPart"]] = relationship("CatalogPart", back_populates="manufacturer", lazy="select")
    materials: Mapped[list["CatalogMaterial"]] = relationship("CatalogMaterial", back_populates="manufacturer", lazy="select")

    def __repr__(self) -> str:
        return f"<CatalogManufacturer id={self.id} code={self.code}>"
