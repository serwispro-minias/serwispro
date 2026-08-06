from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.service_order import ServiceOrder
    from app.models.user import User


SERVICE_ORDER_TIMELINE_TYPE_CHOICES: list[tuple[str, str]] = [
    ("DIAGNOSIS", "Diagnoza"),
    ("REPAIR", "Naprawa"),
    ("CUSTOMER_CONTACT", "Kontakt z klientem"),
    ("PARTS_ORDER", "Zamówienie części"),
    ("TESTS", "Testy"),
    ("INTERNAL_INFO", "Informacja wewnętrzna"),
]

SERVICE_ORDER_TIMELINE_TYPE_LABELS = dict(SERVICE_ORDER_TIMELINE_TYPE_CHOICES)


class ServiceOrderTimelineEntry(BaseTenantModel):
    """Single repair activity entry for a service order."""

    __tablename__ = "service_order_timeline_entries"
    __table_args__ = (
        Index("ix_so_timeline_entries_company_id", "company_id"),
        Index("ix_so_timeline_entries_branch_id", "branch_id"),
        Index("ix_so_timeline_entries_order_id", "service_order_id"),
        Index("ix_so_timeline_entries_author_id", "author_user_id"),
        Index("ix_so_timeline_entries_type", "entry_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_order_id: Mapped[int] = mapped_column(ForeignKey("service_orders.id"), nullable=False)
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    entry_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    parts_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    labor_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    service_order: Mapped["ServiceOrder"] = relationship("ServiceOrder", back_populates="timeline_entries")
    author_user: Mapped["User | None"] = relationship("User", lazy="select")
    attachments: Mapped[list["ServiceOrderTimelineAttachment"]] = relationship(
        "ServiceOrderTimelineAttachment",
        back_populates="entry",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="ServiceOrderTimelineAttachment.created_at.asc()",
    )


class ServiceOrderTimelineAttachment(BaseTenantModel):
    """Attachment linked to one repair activity entry."""

    __tablename__ = "service_order_timeline_attachments"
    __table_args__ = (
        Index("ix_so_timeline_attachments_company_id", "company_id"),
        Index("ix_so_timeline_attachments_branch_id", "branch_id"),
        Index("ix_so_timeline_attachments_entry_id", "entry_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("service_order_timeline_entries.id"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    entry: Mapped["ServiceOrderTimelineEntry"] = relationship("ServiceOrderTimelineEntry", back_populates="attachments")
