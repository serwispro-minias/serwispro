from __future__ import annotations

from datetime import date
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.service_order import ServiceOrder
    from app.models.stock_issue_item import StockIssueItem
    from app.models.user import User


class StockIssueStatusEnum(str, PyEnum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"
    ISSUED = "POSTED"


STOCK_ISSUE_STATUS_CHOICES = [("DRAFT", "Robocze"), ("POSTED", "Zaksięgowane"), ("CANCELLED", "Anulowane")]
STOCK_ISSUE_STATUS_LABELS = dict(STOCK_ISSUE_STATUS_CHOICES)


class StockIssue(BaseTenantModel):
    __tablename__ = "stock_issues"
    __table_args__ = (
        Index("ix_stock_issues_company_id", "company_id"),
        Index("ix_stock_issues_branch_id", "branch_id"),
        Index("ix_stock_issues_order_id", "service_order_id"),
        Index("ix_stock_issues_issued_by", "issued_by"),
        Index("ix_stock_issues_status", "status"),
        Index("ix_stock_issues_issue_date", "issue_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_number: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    service_order_id: Mapped[int | None] = mapped_column(ForeignKey("service_orders.id"), nullable=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=StockIssueStatusEnum.DRAFT.value)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    service_order: Mapped["ServiceOrder"] = relationship("ServiceOrder", lazy="select")
    branch: Mapped["Branch | None"] = relationship("Branch", lazy="select")
    issuer: Mapped["User | None"] = relationship("User", foreign_keys=[issued_by], lazy="select")
    items: Mapped[list["StockIssueItem"]] = relationship("StockIssueItem", back_populates="stock_issue", cascade="all, delete-orphan", lazy="select")