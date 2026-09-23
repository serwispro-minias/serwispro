from __future__ import annotations

from sqlalchemy import Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

class Supplier(BaseTenantModel):
    """Independent supplier card used by purchasing documents."""

    __tablename__ = "suppliers"
    __table_args__ = (
        Index("ix_catalog_suppliers_company_id", "company_id"),
        Index("ix_catalog_suppliers_branch_id", "branch_id"),
        Index("ix_catalog_suppliers_code", "code"),
        Index("ix_catalog_suppliers_name", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    tax_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    contact_person: Mapped[str | None] = mapped_column(String(180), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<Supplier id={self.id} code={self.code}>"


CatalogSupplier = Supplier
