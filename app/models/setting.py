from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel


class Setting(BaseTenantModel):

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    company: Mapped["Company | None"] = relationship("Company", back_populates="settings")

    def __repr__(self) -> str:
        return f"<Setting key={self.key} company_id={self.company_id}>"