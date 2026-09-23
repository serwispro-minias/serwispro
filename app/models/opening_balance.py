from __future__ import annotations

from datetime import date
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Date, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.opening_balance_item import OpeningBalanceItem


class OpeningBalanceStatusEnum(str, PyEnum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class OpeningBalance(BaseTenantModel):
    __tablename__ = "opening_balances"
    __table_args__ = (
        Index("ix_opening_balances_company_id", "company_id"),
        Index("ix_opening_balances_branch_id", "branch_id"),
        Index("ix_opening_balances_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_number: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    document_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=OpeningBalanceStatusEnum.DRAFT.value)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    items: Mapped[list["OpeningBalanceItem"]] = relationship(
        "OpeningBalanceItem", back_populates="opening_balance", cascade="all, delete-orphan", lazy="select"
    )
