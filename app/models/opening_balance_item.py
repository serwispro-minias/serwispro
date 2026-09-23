from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.catalog_part import InventoryItem
    from app.models.opening_balance import OpeningBalance
    from app.models.vat_rate import VatRate


class OpeningBalanceItem(BaseModel):
    __tablename__ = "opening_balance_items"
    __table_args__ = (
        Index("ix_opening_balance_items_balance_id", "opening_balance_id"),
        Index("ix_opening_balance_items_inventory_item_id", "inventory_item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    opening_balance_id: Mapped[int] = mapped_column(ForeignKey("opening_balances.id"), nullable=False)
    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    purchase_price_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    vat_id: Mapped[int | None] = mapped_column(ForeignKey("vat_rates.id"), nullable=True)
    net_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))
    vat_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))
    gross_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))

    opening_balance: Mapped["OpeningBalance"] = relationship("OpeningBalance", back_populates="items", lazy="select")
    inventory_item: Mapped["InventoryItem"] = relationship("InventoryItem", lazy="select")
    vat: Mapped["VatRate | None"] = relationship("VatRate", lazy="select")
