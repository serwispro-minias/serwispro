from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.catalog_material import CatalogMaterial
    from app.models.catalog_part import CatalogPart


class CatalogSupplier(BaseTenantModel):
    """Supplier shared by warehouse items."""

    __tablename__ = "catalog_suppliers"
    __table_args__ = (
        Index("ix_catalog_suppliers_company_id", "company_id"),
        Index("ix_catalog_suppliers_branch_id", "branch_id"),
        Index("ix_catalog_suppliers_code", "code"),
        Index("ix_catalog_suppliers_name", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)

    parts: Mapped[list["CatalogPart"]] = relationship("CatalogPart", back_populates="supplier", lazy="select")
    materials: Mapped[list["CatalogMaterial"]] = relationship("CatalogMaterial", back_populates="supplier", lazy="select")

    def __repr__(self) -> str:
        return f"<CatalogSupplier id={self.id} code={self.code}>"
