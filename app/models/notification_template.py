from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.notification_message import NotificationMessage


class NotificationTemplate(BaseTenantModel):
    """Editable message template for one event/channel pair."""

    __tablename__ = "notification_templates"
    __table_args__ = (
        Index("ix_notification_templates_company_id", "company_id"),
        Index("ix_notification_templates_branch_id", "branch_id"),
        Index("ix_notification_templates_event", "event_key"),
        Index("ix_notification_templates_channel", "channel"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    event_key: Mapped[str] = mapped_column(String(60), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    messages: Mapped[list["NotificationMessage"]] = relationship(
        "NotificationMessage",
        back_populates="template",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<NotificationTemplate id={self.id} event={self.event_key} channel={self.channel}>"
