from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class ServiceOrderNumberCounter(db.Model):
    """Serialized per-company sequence allocation, partitioned by numbering period."""

    __tablename__ = "service_order_number_counters"
    __table_args__ = (
        UniqueConstraint("company_id", "period", name="uq_service_order_number_counter_company_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    period: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_value: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)