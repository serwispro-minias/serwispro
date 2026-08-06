from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.notification_template import NotificationTemplate
    from app.models.service_order import ServiceOrder
    from app.models.user import User


class NotificationMessage(BaseTenantModel):
    """Communication history entry for SMS/e-mail messages."""

    __tablename__ = "notification_logs"
    __table_args__ = (
        Index("ix_notification_logs_company_id", "company_id"),
        Index("ix_notification_logs_branch_id", "branch_id"),
        Index("ix_notification_logs_order_id", "service_order_id"),
        Index("ix_notification_logs_channel", "channel"),
        Index("ix_notification_logs_status", "status"),
        Index("ix_notification_logs_created_at", "created_at"),
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
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    server_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)

    service_order: Mapped["ServiceOrder"] = relationship("ServiceOrder", back_populates="notification_messages", lazy="select")
    template: Mapped["NotificationTemplate | None"] = relationship("NotificationTemplate", back_populates="messages", lazy="select")
    user: Mapped["User | None"] = relationship("User", lazy="select")

    def mark_sent_now(self) -> None:
        self.sent_at = datetime.now(timezone.utc)

    def __repr__(self) -> str:
        return f"<NotificationMessage id={self.id} order_id={self.service_order_id} channel={self.channel} status={self.status}>"
