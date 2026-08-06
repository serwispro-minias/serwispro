from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseTenantModel


class NotificationQueue(BaseTenantModel):
    """Queue table for deferred/retryable notifications."""

    __tablename__ = "notification_queue"
    __table_args__ = (
        Index("ix_notification_queue_company_id", "company_id"),
        Index("ix_notification_queue_branch_id", "branch_id"),
        Index("ix_notification_queue_order_id", "service_order_id"),
        Index("ix_notification_queue_channel", "channel"),
        Index("ix_notification_queue_status", "status"),
        Index("ix_notification_queue_next_retry_at", "next_retry_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_order_id: Mapped[int] = mapped_column(ForeignKey("service_orders.id"), nullable=False)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("notification_templates.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    event_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    recipient: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="QUEUED")
    provider_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<NotificationQueue id={self.id} order_id={self.service_order_id} "
            f"channel={self.channel} status={self.status}>"
        )
