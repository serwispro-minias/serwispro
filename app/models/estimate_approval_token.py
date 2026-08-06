from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.service_estimate import ServiceEstimate


ESTIMATE_APPROVAL_STATUS_CHOICES: list[tuple[str, str]] = [
    ("PENDING", "Oczekuje"),
    ("ACCEPTED", "Zaakceptowany"),
    ("REJECTED", "Odrzucony"),
    ("EXPIRED", "Wygasły"),
]

ESTIMATE_APPROVAL_STATUS_LABELS = dict(ESTIMATE_APPROVAL_STATUS_CHOICES)


class EstimateApprovalToken(BaseTenantModel):
    """One-time public token for customer estimate decision."""

    __tablename__ = "estimate_approval_tokens"
    __table_args__ = (
        Index("ix_estimate_approval_tokens_company_id", "company_id"),
        Index("ix_estimate_approval_tokens_branch_id", "branch_id"),
        Index("ix_estimate_approval_tokens_estimate_id", "estimate_id"),
        Index("ix_estimate_approval_tokens_status", "status"),
        Index("ix_estimate_approval_tokens_expires_at", "expires_at"),
        Index("ix_estimate_approval_tokens_token", "token", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    estimate_id: Mapped[int] = mapped_column(ForeignKey("service_estimates.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    estimate: Mapped["ServiceEstimate"] = relationship("ServiceEstimate", back_populates="approval_tokens", lazy="select")

    @property
    def is_expired(self) -> bool:
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= datetime.now(timezone.utc)

    def __repr__(self) -> str:
        return f"<EstimateApprovalToken id={self.id} estimate_id={self.estimate_id} status={self.status}>"
