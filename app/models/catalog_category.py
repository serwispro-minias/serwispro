from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.catalog_part import InventoryItem


class ProductCategory(BaseTenantModel):
    """Product category used by the warehouse product card."""

    __tablename__ = "product_categories"
    __table_args__ = (
        Index("ix_product_categories_company_id", "company_id"),
        Index("ix_product_categories_branch_id", "branch_id"),
        Index("ix_product_categories_code", "code"),
        Index("ix_product_categories_name", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    inventory_items: Mapped[list["InventoryItem"]] = relationship("InventoryItem", back_populates="category", lazy="select")

    def __repr__(self) -> str:
        return f"<ProductCategory id={self.id} code={self.code}>"


CatalogCategory = ProductCategory
